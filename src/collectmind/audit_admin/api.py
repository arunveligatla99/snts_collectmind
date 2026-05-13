"""Break-glass audit-admin FastAPI router (feature 002 / FR-005a / ADR-0007 Part 5).

DISTINCT router from the regular audit-query path. Mounted at ``/api/v1/audit/break-glass``
with the operator-principal dependency at the router boundary. ADR-0007 Part 5 is explicit:
this surface and the regular audit-query surface share NO handler function and NO code path,
so accidental bypass invocation from the regular flow is a build-time impossibility (the
two paths are different functions on different routers with different dependencies).

Atomic-audit contract (FR-005b + SC-013):
    Every invocation writes a ``kind=break_glass`` row to ``audit_events`` IN THE SAME
    database transaction as the bypassed SELECT. The audit-row INSERT runs FIRST, the SELECT
    runs second, both inside ``conn.transaction()``. If the audit-row INSERT raises, the
    transaction aborts; the SELECT result is never returned to the caller and the response
    is 500.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from collectmind.auth.operator_principal import OperatorPrincipal, authenticated_operator_principal
from collectmind.registry.db import Database

logger = structlog.get_logger(__name__)

ReasonCode = Literal[
    "incident_response",
    "legal_hold",
    "regulator_request",
    "support_escalation",
    "operator_self_audit",
]


class BreakGlassRequest(BaseModel):
    """Request body for ``POST /api/v1/audit/break-glass/query`` (per audit-admin.v1.yaml)."""

    tenant_scope: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    correlation_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    reason_code: ReasonCode


class AuditEvent(BaseModel):
    """Audit event projection returned to operator (subset of audit_events row)."""

    event_id: str
    tenant_id: str
    kind: str
    correlation_id: str
    occurred_at: str
    extras: dict[str, Any] | None = None


class AuditEventList(BaseModel):
    events: list[AuditEvent]
    total: int


router = APIRouter(
    prefix="/api/v1/audit/break-glass",
    tags=["break-glass"],
)


@router.post(
    "/query",
    response_model=AuditEventList,
    status_code=status.HTTP_200_OK,
)
async def break_glass_query(
    payload: BreakGlassRequest,
    request: Request,
    operator: Annotated[OperatorPrincipal, Depends(authenticated_operator_principal)],
) -> AuditEventList:
    """Cross-tenant audit-events read under elevated audit.

    Steps (in this order, inside a single service-principal transaction):
        1. INSERT atomic ``kind=break_glass`` row recording the operator + scope + reason.
        2. SELECT the named tenant_scope's audit_events for the named correlation_id.
        3. Return the rows.

    Step (1) is FIRST so an audit-write failure aborts the txn BEFORE the SELECT result is
    materialized. ``ON CONFLICT DO NOTHING`` on the audit writer means a retried invocation
    with the same correlation_id is idempotent on the audit chain (one row per incident).
    """
    db: Database = request.app.state.db
    event_id = uuid.uuid4().hex
    extras = {
        "operator_principal_subject": operator.subject,
        "tenant_scope": payload.tenant_scope,
        "reason_code": payload.reason_code,
    }

    async with db.acquire_service_principal() as conn, conn.transaction():
        # Step 1: atomic audit row. INSERT runs under the service-principal connection
        # (BYPASSRLS) so the audit row lands regardless of any tenant-scoped RLS policy.
        await conn.execute(
            """
            INSERT INTO audit_events (
              event_id, tenant_id, kind, originating_finding,
              principal_subject, correlation_id, occurred_at
            ) VALUES ($1, $2, 'break_glass', $3::jsonb, $4, $5, now())
            ON CONFLICT (correlation_id, kind) DO NOTHING
            """,
            event_id,
            payload.tenant_scope,
            json.dumps(extras),
            operator.subject,
            payload.correlation_id,
        )

        # Step 2: bypassed SELECT — parameterized on the tenant_scope. Cannot widen mid-flight.
        rows = await conn.fetch(
            """
            SELECT event_id, tenant_id, kind, correlation_id, occurred_at,
                   originating_finding, policy_ref, deployment_ref, outcome_ref
            FROM audit_events
            WHERE tenant_id = $1 AND correlation_id = $2
            ORDER BY occurred_at ASC
            """,
            payload.tenant_scope,
            payload.correlation_id,
        )

    events: list[AuditEvent] = []
    for row in rows:
        row_extras: dict[str, Any] = {}
        for key in ("originating_finding", "policy_ref", "deployment_ref", "outcome_ref"):
            value = row[key]
            if value is None:
                continue
            row_extras[key] = json.loads(value) if isinstance(value, str) else value
        events.append(
            AuditEvent(
                event_id=str(row["event_id"]),
                tenant_id=str(row["tenant_id"]),
                kind=str(row["kind"]),
                correlation_id=str(row["correlation_id"]),
                occurred_at=row["occurred_at"].isoformat(),
                extras=row_extras or None,
            )
        )

    logger.info(
        "break_glass_query",
        operator=operator.subject,
        tenant_scope=payload.tenant_scope,
        reason_code=payload.reason_code,
        rows=len(events),
    )

    if not events:
        # No matching rows. Per audit-admin.v1.yaml 404 contract.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_events", "message": "no audit events match"},
        )

    return AuditEventList(events=events, total=len(events))
