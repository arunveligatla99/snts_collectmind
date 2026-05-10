"""ErasureDispatcher (T100). Per-store dispatch with audit trail."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog

from collectmind.models.erasure import ErasureRequest
from collectmind.registry.audit import AuditEventWriter
from collectmind.registry.db import Database


logger = structlog.get_logger(__name__)


class ErasureDispatcher:
    def __init__(self, db: Database, audit_writer: AuditEventWriter) -> None:
        self._db = db
        self._audit_writer = audit_writer

    async def submit(
        self,
        *,
        request_id: str,
        tenant_id: str,
        requested_by: str,
        requested_at: datetime,
        target_completion_at: datetime,
        payload: ErasureRequest,
    ) -> None:
        async with self._db.acquire(tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO erasure_requests (
                  request_id, tenant_id, subject_kind, subject_identifier,
                  requested_by, requested_at, target_completion_at, status,
                  per_store_status, mode
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'requested', $8::jsonb, $9)
                """,
                request_id,
                tenant_id,
                payload.subject_kind,
                payload.subject_identifier,
                requested_by,
                requested_at,
                target_completion_at,
                json.dumps({"registry": "pending", "telemetry": "pending", "audit": "pending"}),
                payload.mode,
            )

        await self._audit_writer.write(
            tenant_id=tenant_id,
            kind="erasure",
            correlation_id=request_id,
            principal_subject=requested_by,
        )

        # Dispatch in background; small enough to run synchronously here.
        asyncio.create_task(self._dispatch(tenant_id, request_id, payload))

    async def _dispatch(self, tenant_id: str, request_id: str, payload: ErasureRequest) -> None:
        per_store: dict[str, str] = {"registry": "pending", "telemetry": "pending", "audit": "pending"}
        try:
            await self._erase_registry(tenant_id, payload)
            per_store["registry"] = "erased" if payload.mode == "erased" else "redacted"
        except Exception as exc:  # noqa: BLE001
            logger.error("erasure_registry_failed", error=str(exc), request_id=request_id)
            per_store["registry"] = "failed"

        try:
            await self._erase_telemetry(tenant_id, payload)
            per_store["telemetry"] = "erased"
        except Exception as exc:  # noqa: BLE001
            logger.error("erasure_telemetry_failed", error=str(exc), request_id=request_id)
            per_store["telemetry"] = "failed"

        try:
            await self._redact_audit(tenant_id, payload)
            per_store["audit"] = "redacted"
        except Exception as exc:  # noqa: BLE001
            logger.error("erasure_audit_failed", error=str(exc), request_id=request_id)
            per_store["audit"] = "failed"

        status = "completed" if all(v in {"erased", "redacted"} for v in per_store.values()) else "partial"
        async with self._db.acquire(tenant_id) as conn:
            await conn.execute(
                """
                UPDATE erasure_requests
                SET status = $1, per_store_status = $2::jsonb, completed_at = $3
                WHERE request_id = $4
                """,
                status,
                json.dumps(per_store),
                datetime.now(tz=timezone.utc),
                request_id,
            )

    async def _erase_registry(self, tenant_id: str, payload: ErasureRequest) -> None:
        if payload.subject_kind != "vehicle":
            return
        async with self._db.acquire(tenant_id) as conn:
            await conn.execute("SELECT set_config('collectmind.erasure', 'on', true)")
            await conn.execute(
                """
                UPDATE collection_policies
                SET vehicle_scope = (
                  SELECT jsonb_agg(elem)
                  FROM jsonb_array_elements(vehicle_scope) AS elem
                  WHERE elem::text <> to_jsonb($2::text)::text
                )
                WHERE tenant_id = $1
                  AND vehicle_scope @> jsonb_build_array($2::text)
                """,
                tenant_id,
                payload.subject_identifier,
            )

    async def _erase_telemetry(self, tenant_id: str, payload: ErasureRequest) -> None:
        if payload.subject_kind != "vehicle":
            return
        async with self._db.acquire(tenant_id) as conn:
            await conn.execute(
                "DELETE FROM telemetry_observations WHERE tenant_id = $1 AND vehicle_id = $2",
                tenant_id,
                payload.subject_identifier,
            )

    async def _redact_audit(self, tenant_id: str, payload: ErasureRequest) -> None:
        # Audit is always redacted (never deleted) to preserve referential integrity.
        async with self._db.acquire(tenant_id) as conn:
            await conn.execute("SELECT set_config('collectmind.erasure', 'on', true)")
            await conn.execute(
                """
                UPDATE audit_events
                SET originating_finding = jsonb_set(
                  COALESCE(originating_finding, '{}'::jsonb),
                  '{redacted_subject}',
                  to_jsonb($2::text)
                )
                WHERE tenant_id = $1
                  AND (originating_finding ->> 'finding_id' = $2 OR principal_subject = $2)
                """,
                tenant_id,
                payload.subject_identifier,
            )

    async def get(self, tenant_id: str, request_id: str) -> dict[str, Any] | None:
        async with self._db.acquire(tenant_id) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM erasure_requests WHERE tenant_id = $1 AND request_id = $2",
                tenant_id,
                request_id,
            )
        if row is None:
            return None
        d = dict(row)
        if isinstance(d.get("per_store_status"), str):
            d["per_store_status"] = json.loads(d["per_store_status"])
        for key in ("requested_at", "target_completion_at", "completed_at"):
            v = d.get(key)
            if isinstance(v, datetime):
                d[key] = v.isoformat()
        return {
            "request_id": d["request_id"],
            "tenant_id": d["tenant_id"],
            "subject_kind": d["subject_kind"],
            "subject_identifier": d["subject_identifier"],
            "requested_by": d["requested_by"],
            "requested_at": d["requested_at"],
            "target_completion_at": d["target_completion_at"],
            "status": d["status"],
            "per_store_status": d["per_store_status"],
            "mode": d["mode"],
            "completed_at": d["completed_at"],
        }
