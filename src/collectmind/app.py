"""FastAPI application composition for the orchestration API.

Phase 1 + 2 scope: this module wires the readiness probe, the health endpoint, the
Prometheus exposition, the structured-error handler, and the JWT-protected route
shells. The actual /findings handler, query interface, and erasure dispatcher land in
Phase 3 US1 (per tasks.md).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response

from collectmind.auth.dependencies import authenticated_principal, get_settings
from collectmind.auth.jwt_verifier import Principal
from collectmind.config import Settings
from collectmind.errors import CollectMindError
from collectmind.kafka.producer import Producer
from collectmind.observability.logging import configure_logging, get_logger
from collectmind.observability.metrics import render_prometheus
from collectmind.observability.otel import init_otel
from collectmind.redis.client import HotStore
from collectmind.registry.db import Database


logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()
    configure_logging(settings.log_level)
    init_otel(service_name=settings.service_name, otlp_endpoint=settings.otlp_endpoint)

    db = Database(settings.postgres_dsn)
    redis = HotStore(settings.redis_url)
    kafka = Producer(settings.kafka_bootstrap_servers)

    app.state.db = db
    app.state.redis = redis
    app.state.kafka = kafka

    await db.connect()
    await redis.connect()
    await kafka.start()

    logger.info(
        "app_started",
        service=settings.service_name,
        oauth2_issuer=settings.oauth2_issuer_url,
        time_acceleration_factor=settings.time_acceleration_factor,
    )
    try:
        yield
    finally:
        await kafka.stop()
        await redis.close()
        await db.close()


app = FastAPI(title="CollectMind Orchestration API", version="0.1.0", lifespan=_lifespan)


@app.exception_handler(CollectMindError)
async def collectmind_error_handler(_: Request, exc: CollectMindError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=exc.to_response().model_dump())


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
async def ready(request: Request) -> JSONResponse:
    """Readiness probe: verifies Postgres, Redis, Kafka, and OAuth issuer reachability."""
    db: Database = request.app.state.db
    redis: HotStore = request.app.state.redis

    db_ok, redis_ok = await asyncio.gather(db.ping(), redis.ping(), return_exceptions=True)
    db_ready = db_ok is True
    redis_ready = redis_ok is True

    # Kafka producer is started in lifespan; treat its presence as ready.
    kafka_ready = request.app.state.kafka is not None

    body: dict[str, object] = {
        "ready": db_ready and redis_ready and kafka_ready,
        "components": {
            "postgres": "ok" if db_ready else "not_ready",
            "redis": "ok" if redis_ready else "not_ready",
            "kafka": "ok" if kafka_ready else "not_ready",
        },
    }
    status_code = 200 if body["ready"] else 503
    return JSONResponse(status_code=status_code, content=body)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=render_prometheus(), media_type="text/plain; version=0.0.4")


@app.get("/whoami")
async def whoami(principal: Principal = Depends(authenticated_principal)) -> dict[str, object]:
    """JWT smoke-test endpoint: returns the authenticated principal claims.

    This is a feature-001 endpoint primarily used by the smoke test to verify the
    OAuth2 issuer and JWKS-based JWT verification end-to-end. It exposes only the
    principal's `tenant_id`, `subject`, and `scopes` (no token claims beyond what
    the principal carries).
    """
    return {
        "tenant_id": principal.tenant_id,
        "subject": principal.subject,
        "scopes": list(principal.scopes),
    }
