"""POST /findings handler (T094). Auth, schema, schema_version, idempotency."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
import ulid
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from collectmind.auth.dependencies import authenticated_principal
from collectmind.auth.jwt_verifier import Principal
from collectmind.errors import SchemaValidationFailed, SchemaVersionUnsupported
from collectmind.graph.session import PolicyGenerationSession
from collectmind.ingest.idempotency import IdempotencyChecker
from collectmind.ingest.schema_version import SchemaVersionChecker
from collectmind.models.finding import DiagnosticFinding
from collectmind.observability.metrics import (
    diagnostic_findings_received_total,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post("/api/v1/findings", status_code=202)
async def post_finding(
    request: Request,
    principal: Principal = Depends(authenticated_principal),
    x_telemetry_simulator_directive: str | None = Header(default=None, alias="X-Telemetry-Simulator-Directive"),
    x_time_acceleration_factor: str | None = Header(default=None, alias="X-Time-Acceleration-Factor"),
) -> JSONResponse:
    body: dict[str, Any] = await request.json()

    schema_check: SchemaVersionChecker = request.app.state.schema_checker
    sv = schema_check.check(body.get("schema_version"))
    if not sv.ok and sv.code == "SCHEMA_VERSION_UNSUPPORTED":
        raise SchemaVersionUnsupported(
            requested=body.get("schema_version", ""),
            supported_major=str(sv.supported_major),
        )
    if not sv.ok:
        raise SchemaValidationFailed(field="schema_version", message="malformed semver")

    try:
        finding = DiagnosticFinding.model_validate(body)
    except ValidationError as exc:
        # Surface the first invalid field for ergonomics; full errors in details.
        first = exc.errors()[0] if exc.errors() else {"loc": ["unknown"], "msg": "invalid"}
        raise SchemaValidationFailed(
            field=".".join(str(p) for p in first.get("loc", ["unknown"])),
            message=str(first.get("msg", "validation error")),
        )

    payload_canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_sha = hashlib.sha256(payload_canonical).digest()

    correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    accepted_at = datetime.now(tz=UTC)

    idempotency: IdempotencyChecker = request.app.state.idempotency
    decision = await idempotency.check_or_record(principal.tenant_id, finding.finding_id, payload_sha=payload_sha)

    diagnostic_findings_received_total.labels(tenant_id=principal.tenant_id).inc()

    if decision.first_seen:
        await _persist_finding(request, principal, finding, payload_sha, correlation_id, accepted_at)
        await _enqueue(
            request,
            principal,
            finding,
            correlation_id,
            x_telemetry_simulator_directive,
            x_time_acceleration_factor,
        )
        return JSONResponse(
            status_code=202,
            content={
                "tenant_id": principal.tenant_id,
                "finding_id": finding.finding_id,
                "correlation_id": correlation_id,
                "accepted_at": accepted_at.isoformat(),
                "policy_id": f"policy-{finding.finding_id}",
                "idempotent_replay": False,
            },
        )

    # Idempotent replay path.
    return JSONResponse(
        status_code=202,
        content={
            "tenant_id": principal.tenant_id,
            "finding_id": finding.finding_id,
            "correlation_id": correlation_id,
            "accepted_at": accepted_at.isoformat(),
            "policy_id": f"policy-{finding.finding_id}",
            "idempotent_replay": True,
        },
    )


async def _persist_finding(
    request: Request,
    principal: Principal,
    finding: DiagnosticFinding,
    payload_sha: bytes,
    correlation_id: str,
    accepted_at: datetime,
) -> None:
    db = request.app.state.db
    async with db.acquire(principal.tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO diagnostic_findings (
              tenant_id, finding_id, schema_version, anomaly_type, hypothesis_class,
              hypothesis_statement, candidate_signals, vehicle_scope, upstream_confidence,
              received_at, received_payload_sha256
            ) VALUES (
              $1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9,$10,$11
            )
            ON CONFLICT (tenant_id, finding_id) DO NOTHING
            """,
            principal.tenant_id,
            finding.finding_id,
            finding.schema_version,
            finding.anomaly_type,
            finding.hypothesis_class,
            finding.hypothesis_statement,
            json.dumps(finding.candidate_signals),
            json.dumps(finding.vehicle_scope),
            float(finding.upstream_confidence),
            accepted_at,
            payload_sha,
        )

    await request.app.state.audit_writer.write(
        tenant_id=principal.tenant_id,
        kind="accepted",
        correlation_id=correlation_id,
        principal_subject=principal.subject,
        originating_finding={"tenant_id": principal.tenant_id, "finding_id": finding.finding_id},
        inbound_schema_version=finding.schema_version,
    )


async def _enqueue(
    request: Request,
    principal: Principal,
    finding: DiagnosticFinding,
    correlation_id: str,
    sim_directive: str | None,
    accel_header: str | None,
) -> None:
    """Run the LangGraph in-process for foundation builds; production goes through Kafka."""
    session = PolicyGenerationSession(
        session_id=str(ulid.new()),
        tenant_id=principal.tenant_id,
        correlation_id=correlation_id,
        originating_finding={
            "tenant_id": principal.tenant_id,
            "finding_id": finding.finding_id,
            "schema_version": finding.schema_version,
            "anomaly_type": finding.anomaly_type,
            "hypothesis_class": finding.hypothesis_class,
            "hypothesis_statement": finding.hypothesis_statement,
            "candidate_signals": list(finding.candidate_signals),
            "vehicle_scope": list(finding.vehicle_scope),
            "upstream_confidence": float(finding.upstream_confidence),
        },
        started_at=datetime.now(tz=UTC),
    )
    runner = request.app.state.graph_runner
    asyncio.create_task(runner.run_async(session, sim_directive=sim_directive, accel_header=accel_header))
