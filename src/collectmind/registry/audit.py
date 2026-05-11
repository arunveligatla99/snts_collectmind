"""AuditEventWriter (T086 + T209). Enforces FR-017a + feature-002 minimum field sets.

Feature 002 extension:
    - Accepts four new audit-row kinds: break_glass, tenant_config_change,
      deployment_rejected, vehicle_assignment_change.
    - Enforces per-kind minimum field sets at write time (mirrors the kind=generated
      FR-017a pattern from feature 001).
    - Uses ON CONFLICT DO NOTHING against the UNIQUE (correlation_id, kind) constraint
      shipped by migration 016 (closes feature-001 Flag 9 deferral).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import ulid

from collectmind.registry.db import Database

# Per-kind required-field maps for feature-002 audit kinds. Feature-001 kind=generated
# still uses the inline check below; the new kinds use the _extras['minimum_field_set']
# carrier on originating_finding (mirrors feature-001 Flag 10 _extras hack).
_KIND_MIN_FIELDS: dict[str, tuple[str, ...]] = {
    "break_glass": ("operator_principal_subject", "tenant_scope", "reason_code"),
    "tenant_config_change": ("service_principal_subject", "target_tenant_id"),
    "deployment_rejected": (
        "policy_ref",
        "target_vehicle_id",
        "policy_declared_tenant_id",
        "vehicle_owning_tenant_id",
    ),
    "vehicle_assignment_change": (
        "service_principal_subject",
        "vehicle_id",
        "new_tenant_id",
        "reason_code",
    ),
}


class AuditEventWriter:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def write(
        self,
        *,
        tenant_id: str,
        kind: str,
        correlation_id: str,
        principal_subject: str,
        originating_finding: dict[str, Any] | None = None,
        policy_ref: dict[str, Any] | None = None,
        deployment_ref: dict[str, Any] | None = None,
        outcome_ref: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        slm_repo: str | None = None,
        slm_revision_sha: str | None = None,
        slm_runtime: str | None = None,
        slm_runtime_version: str | None = None,
        slm_quantization: str | None = None,
        slm_decoding_seed: int | None = None,
        prompt_template_version: str | None = None,
        inbound_schema_version: str | None = None,
        time_acceleration_factor: float | None = None,
    ) -> str:
        if kind == "generated":
            missing = [
                name
                for name, value in {
                    "slm_repo": slm_repo,
                    "slm_revision_sha": slm_revision_sha,
                    "slm_runtime": slm_runtime,
                    "slm_runtime_version": slm_runtime_version,
                    "slm_quantization": slm_quantization,
                    "slm_decoding_seed": slm_decoding_seed,
                    "prompt_template_version": prompt_template_version,
                }.items()
                if value is None
            ]
            if missing:
                raise ValueError(f"audit kind=generated missing required fields: {missing}")
        elif kind in _KIND_MIN_FIELDS:
            payload = originating_finding or {}
            missing = [field for field in _KIND_MIN_FIELDS[kind] if field not in payload]
            if missing:
                raise ValueError(f"audit kind={kind} missing required fields: {missing}")
        event_id = str(ulid.new())
        async with self._db.acquire(tenant_id) as conn:
            extras: dict[str, Any] = {}
            if error is not None:
                extras["error"] = error
            originating_with_extras = dict(originating_finding or {})
            if extras:
                originating_with_extras.setdefault("_extras", extras)
            # ON CONFLICT DO NOTHING against UNIQUE (correlation_id, kind) per migration 016.
            # Retry-safe: a duplicate (correlation_id, kind) write coalesces to the prior row.
            # The returned event_id reflects the persisted-row id (existing-on-conflict).
            row = await conn.fetchrow(
                """
                INSERT INTO audit_events (
                  event_id, tenant_id, kind, originating_finding, policy_ref,
                  deployment_ref, outcome_ref, slm_repo, slm_revision_sha, slm_runtime,
                  slm_runtime_version, slm_quantization, slm_decoding_seed,
                  prompt_template_version, inbound_schema_version,
                  time_acceleration_factor, principal_subject, correlation_id, occurred_at
                ) VALUES (
                  $1,$2,$3,$4::jsonb,$5::jsonb,$6::jsonb,$7::jsonb,
                  $8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19
                )
                ON CONFLICT (correlation_id, kind) DO NOTHING
                RETURNING event_id
                """,
                event_id,
                tenant_id,
                kind,
                json.dumps(originating_with_extras) if originating_with_extras else None,
                json.dumps(policy_ref) if policy_ref else None,
                json.dumps(deployment_ref) if deployment_ref else None,
                json.dumps(outcome_ref) if outcome_ref else None,
                slm_repo,
                slm_revision_sha,
                slm_runtime,
                slm_runtime_version,
                slm_quantization,
                slm_decoding_seed,
                prompt_template_version,
                inbound_schema_version,
                time_acceleration_factor,
                principal_subject,
                correlation_id,
                datetime.now(tz=UTC),
            )
            if row is None:
                existing = await conn.fetchrow(
                    "SELECT event_id FROM audit_events WHERE correlation_id = $1 AND kind = $2",
                    correlation_id,
                    kind,
                )
                if existing is None:
                    raise RuntimeError(
                        f"audit upsert returned no row and no existing row for "
                        f"(correlation_id={correlation_id}, kind={kind})"
                    )
                return str(existing["event_id"])
            return str(row["event_id"])

    async def list_for_correlation(self, tenant_id: str, correlation_id: str) -> list[dict[str, Any]]:
        async with self._db.acquire(tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM audit_events
                WHERE tenant_id = $1 AND correlation_id = $2
                ORDER BY occurred_at ASC
                """,
                tenant_id,
                correlation_id,
            )
        return [_row_to_event(r) for r in rows]


def _row_to_event(row: Any) -> dict[str, Any]:
    d = dict(row)
    for k in ("originating_finding", "policy_ref", "deployment_ref", "outcome_ref"):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    error = None
    if isinstance(d.get("originating_finding"), dict):
        extras = d["originating_finding"].get("_extras") or {}
        if "error" in extras:
            error = extras["error"]
    return {
        "event_id": d["event_id"],
        "tenant_id": d["tenant_id"],
        "kind": d["kind"],
        "correlation_id": d["correlation_id"],
        "principal_subject": d["principal_subject"],
        "occurred_at": d["occurred_at"].isoformat()
        if isinstance(d.get("occurred_at"), datetime)
        else d.get("occurred_at"),
        "originating_finding": d.get("originating_finding"),
        "policy_ref": d.get("policy_ref"),
        "deployment_ref": d.get("deployment_ref"),
        "outcome_ref": d.get("outcome_ref"),
        "error": error,
        "slm_repo": d.get("slm_repo"),
        "slm_revision_sha": d.get("slm_revision_sha"),
        "slm_runtime": d.get("slm_runtime"),
        "slm_runtime_version": d.get("slm_runtime_version"),
        "slm_quantization": d.get("slm_quantization"),
        "slm_decoding_seed": int(d["slm_decoding_seed"]) if d.get("slm_decoding_seed") is not None else None,
        "prompt_template_version": d.get("prompt_template_version"),
        "inbound_schema_version": d.get("inbound_schema_version"),
        "time_acceleration_factor": float(d["time_acceleration_factor"])
        if d.get("time_acceleration_factor") is not None
        else None,
    }
