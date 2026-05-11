"""FastAPI application composition (T104).

Wires the orchestration router (POST /findings), the query router, the erasure router,
the LangGraph runner, the feedback worker, the deterministic stub or real SLM client,
and the per-feature observability stack.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from collectmind.audit_admin.api import router as audit_admin_router
from collectmind.auth.dependencies import get_settings
from collectmind.config import Settings
from collectmind.deployer.signing import LocalKeySigner
from collectmind.deployer.simulator import SimulatorCollectorAIClient
from collectmind.erasure.api import router as erasure_router
from collectmind.erasure.dispatcher import ErasureDispatcher
from collectmind.errors import CollectMindError
from collectmind.feedback.scheduler import LogicalTimeScheduler
from collectmind.feedback.worker import FeedbackWorker
from collectmind.graph.build import CollectMindGraph
from collectmind.graph.policy_deployer import PolicyDeployer
from collectmind.graph.policy_generator import PolicyGenerator
from collectmind.graph.policy_validator import PolicyValidatorNode
from collectmind.graph.runner import GraphRunner
from collectmind.ingest.http import router as ingest_router
from collectmind.ingest.idempotency import IdempotencyChecker
from collectmind.ingest.schema_version import SchemaVersionChecker
from collectmind.kafka.producer import Producer
from collectmind.observability.logging import configure_logging, get_logger
from collectmind.observability.metrics import (
    http_request_total,
    query_request_latency_seconds,
    render_prometheus,
)
from collectmind.observability.otel import init_otel
from collectmind.query.api import router as query_router
from collectmind.redis.client import HotStore
from collectmind.registry.audit import AuditEventWriter
from collectmind.registry.db import Database
from collectmind.registry.migrations.runner import apply_pending
from collectmind.registry.repository import (
    DeploymentRepository,
    OutcomeRepository,
    PolicyRepository,
)
from collectmind.registry.tenant_config import TenantConfigRepository
from collectmind.registry.tenant_vehicles import TenantVehiclesRepository
from collectmind.simulators.telemetry_generator import TelemetryGenerator
from collectmind.slm.client import PolicyGeneratorClient
from collectmind.slm.stub_client import FingerprintStubClient
from collectmind.validator.policy_validator import PolicyValidator

logger = get_logger(__name__)


def _resolve_corpus_root() -> Path:
    env = os.environ.get("POLICY_CORPUS_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    # Container layout: /app/collectmind/app.py -> /app/tests/fixtures/policy_corpus
    container_path = here.parent.parent / "tests" / "fixtures" / "policy_corpus"
    if container_path.exists():
        return container_path
    # Repo layout: src/collectmind/app.py -> repo_root/tests/fixtures/policy_corpus
    return here.parents[2] / "tests" / "fixtures" / "policy_corpus"


_CORPUS_ROOT = _resolve_corpus_root()


def _select_policy_client() -> PolicyGeneratorClient:
    profile = os.environ.get("SLM_PROFILE", "dev_default").lower()
    env = os.environ.get("COLLECTMIND_ENV", "local").lower()
    if profile == "vllm":
        from collectmind.slm.vllm_client import VLLMClient

        return VLLMClient.from_env()
    if profile in {"cpu", "llama_cpp"}:
        from collectmind.slm.llamacpp_client import LlamaCppClient

        return LlamaCppClient.from_env()
    if profile == "stub":
        return FingerprintStubClient(corpus_root=_CORPUS_ROOT)
    # dev_default fallback. Refuse in any non-local environment (ADR-0006).
    if env != "local":
        raise RuntimeError(
            f"SLM_PROFILE=dev_default is not allowed when COLLECTMIND_ENV={env!r}. "
            "Per ADR-0006, the DevDefaultPolicyClient is gated to local-only "
            "foundation smoke. Set SLM_PROFILE to one of {vllm, cpu, stub}."
        )
    from collectmind.slm.dev_default_client import DevDefaultPolicyClient

    return DevDefaultPolicyClient()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()
    configure_logging(settings.log_level)
    init_otel(service_name=settings.service_name, otlp_endpoint=settings.otlp_endpoint)

    db = Database(settings.postgres_dsn)
    redis = HotStore(settings.redis_url)
    kafka = Producer(settings.kafka_bootstrap_servers)

    # Feature 002 T233: opt-in migration runner on startup. Default OFF so the existing
    # docker-entrypoint-initdb.d path (fresh-volume init) keeps working. Set
    # ``MIGRATIONS_AUTO_APPLY=true`` to apply pending migrations on every container start.
    if os.environ.get("MIGRATIONS_AUTO_APPLY", "false").lower() == "true":
        applied = await apply_pending(settings.postgres_dsn)
        if applied:
            logger.info("migrations_applied_at_startup", versions=applied)

    await db.connect()
    await redis.connect()
    await kafka.start()

    policy_repo = PolicyRepository(db)
    deployment_repo = DeploymentRepository(db)
    outcome_repo = OutcomeRepository(db)
    audit_writer = AuditEventWriter(db)
    erasure_dispatcher = ErasureDispatcher(db, audit_writer)
    tenant_config_repo = TenantConfigRepository(db)
    tenant_vehicles_repo = TenantVehiclesRepository(db)

    signing_key_path = Path(os.environ.get("SIGNING_KEY_PATH", "./models/dev-signing.key"))
    signer = LocalKeySigner.from_path(signing_key_path, key_id="dev-key-1")

    policy_client = _select_policy_client()
    generator = PolicyGenerator(policy_client)
    validator = PolicyValidatorNode(PolicyValidator())
    deployer_node = PolicyDeployer(SimulatorCollectorAIClient.from_env(), signer)
    graph = CollectMindGraph(generator=generator, validator=validator, deployer=deployer_node)

    scheduler = LogicalTimeScheduler(settings.time_acceleration_factor)
    telemetry = TelemetryGenerator(db)
    runner = GraphRunner(
        graph=graph,
        policy_repo=policy_repo,
        deployment_repo=deployment_repo,
        audit_writer=audit_writer,
        telemetry_generator=telemetry,
        signer=signer,
        scheduler=scheduler,
    )
    feedback = FeedbackWorker(
        db=db,
        deployment_repo=deployment_repo,
        policy_repo=policy_repo,
        outcome_repo=outcome_repo,
        audit_writer=audit_writer,
        scheduler=scheduler,
    )

    app.state.db = db
    app.state.redis = redis
    app.state.kafka = kafka
    app.state.policy_repo = policy_repo
    app.state.deployment_repo = deployment_repo
    app.state.outcome_repo = outcome_repo
    app.state.audit_writer = audit_writer
    app.state.erasure_dispatcher = erasure_dispatcher
    app.state.signer = signer
    app.state.graph_runner = runner
    app.state.feedback_worker = feedback
    app.state.scheduler = scheduler
    app.state.signing_key_id = signer.key_id
    app.state.idempotency = IdempotencyChecker.from_db(db)
    app.state.schema_checker = SchemaVersionChecker(supported_major=1)
    app.state.tenant_config_repo = tenant_config_repo
    app.state.tenant_vehicles_repo = tenant_vehicles_repo

    feedback_task = asyncio.create_task(feedback.run_forever())

    logger.info(
        "app_started",
        service=settings.service_name,
        oauth2_issuer=settings.oauth2_issuer_url,
        slm_profile=os.environ.get("SLM_PROFILE", "stub"),
        time_acceleration_factor=settings.time_acceleration_factor,
    )
    try:
        yield
    finally:
        feedback.stop()
        feedback_task.cancel()
        try:
            await feedback_task
        except (asyncio.CancelledError, Exception):
            pass
        await kafka.stop()
        await redis.close()
        await db.close()


_ID_SEGMENT = re.compile(r"^[A-Za-z0-9_\-.]{1,256}$")
_QUERY_ROUTE_PREFIXES: tuple[str, ...] = (
    "GET /api/v1/policies",
    "GET /api/v1/vehicle-groups",
    "GET /api/v1/findings/:id/outcome",
    "GET /api/v1/audit",
    "GET /api/v1/erasure-requests",
)


def _normalize_route(method: str, path: str) -> str:
    """Collapse path parameters to `:id` so route cardinality stays bounded.

    Returns "<METHOD> <template>" — e.g. ``GET /api/v1/policies/:id/versions``.
    Unknown paths fall through to ``<METHOD> other``."""
    segments = [s for s in path.split("/") if s]
    out: list[str] = []
    for seg in segments:
        if _ID_SEGMENT.match(seg) and any(c.isdigit() or c in "_-." for c in seg):
            # Heuristic: looks like a path-parameter identifier (has a digit or
            # delimiter, not a bare static segment).
            out.append(":id")
        else:
            out.append(seg)
    template = "/" + "/".join(out) if out else "/"
    return f"{method.upper()} {template}"


def _is_query_route(route: str) -> bool:
    return any(route.startswith(prefix) for prefix in _QUERY_ROUTE_PREFIXES)


class _MetricsMiddleware(BaseHTTPMiddleware):
    """Emits http_request_total and (for query routes) query_request_latency_seconds.

    Wraps every HTTP request handled by the orchestration + query + erasure
    routers. Per Constitution Principle V the surface is RED metrics for every
    external interface; per SC-004 the query latency histogram is the
    measurement vehicle for the p95<=200ms target.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        elapsed = time.monotonic() - start
        route = _normalize_route(request.method, request.url.path)
        status_class = f"{response.status_code // 100}xx"
        http_request_total.labels(route=route, status_class=status_class).inc()
        if _is_query_route(route):
            query_request_latency_seconds.labels(route=route, status_class=status_class).observe(elapsed)
        return response


app = FastAPI(title="CollectMind Orchestration API", version="0.1.0", lifespan=_lifespan)
app.add_middleware(_MetricsMiddleware)
app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(erasure_router)
# T238: break-glass router mounted as a DISTINCT router with its own operator-principal
# dependency at the router boundary (ADR-0007 Part 5). FastAPI cannot route a request to
# any handler inside this router unless the operator JWT audience claim is verified first.
app.include_router(audit_admin_router)


@app.exception_handler(CollectMindError)
async def collectmind_error_handler(_: Request, exc: CollectMindError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=exc.to_response().model_dump())


@app.get("/health", include_in_schema=False)
@app.get("/api/v1/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
@app.get("/api/v1/ready", include_in_schema=False)
async def ready(request: Request) -> JSONResponse:
    db: Database = request.app.state.db
    redis: HotStore = request.app.state.redis
    db_ok, redis_ok = await asyncio.gather(db.ping(), redis.ping(), return_exceptions=True)
    db_ready = db_ok is True
    redis_ready = redis_ok is True
    kafka_ready = request.app.state.kafka is not None
    body: dict[str, object] = {
        "ready": db_ready and redis_ready and kafka_ready,
        "components": {
            "postgres": "ok" if db_ready else "not_ready",
            "redis": "ok" if redis_ready else "not_ready",
            "kafka": "ok" if kafka_ready else "not_ready",
        },
    }
    return JSONResponse(status_code=200 if body["ready"] else 503, content=body)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=render_prometheus(), media_type="text/plain; version=0.0.4")
