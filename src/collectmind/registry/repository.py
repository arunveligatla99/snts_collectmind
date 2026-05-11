"""Registry repositories (T085). Immutable policies, deployments, outcomes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import asyncpg

from collectmind.registry.db import Database


class PolicyRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def insert(self, tenant_id: str, policy: dict[str, Any], audit_meta: dict[str, Any]) -> None:
        async with self._db.acquire(tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO collection_policies (
                  tenant_id, policy_id, version, signal_spec, trigger_conditions,
                  collection_window_hours_logical, vehicle_scope, hypothesis_statement,
                  data_governance_flags, confidence_threshold, generated_from_session_id,
                  originating_finding, prompt_template_version, slm_repo, slm_revision_sha,
                  slm_runtime, slm_runtime_version, slm_quantization, slm_decoding_seed,
                  payload_signature, signature_key_id, created_at
                ) VALUES (
                  $1,$2,$3,$4::jsonb,$5::jsonb,$6,$7::jsonb,$8,$9::jsonb,$10,$11,
                  $12::jsonb,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22
                )
                """,
                tenant_id,
                policy["policy_id"],
                policy["version"],
                json.dumps(policy["signals"]),
                json.dumps(policy.get("trigger_conditions", [])),
                int(policy["collection_window_hours"]),
                json.dumps(policy["vehicle_scope"]),
                policy.get("hypothesis", ""),
                json.dumps(policy["data_governance_flags"]),
                float(policy["confidence_threshold"]),
                policy["generated_from_session_id"],
                json.dumps(policy["originating_finding"]),
                audit_meta["prompt_template_version"],
                audit_meta["slm_repo"],
                audit_meta["slm_revision_sha"],
                audit_meta["slm_runtime"],
                audit_meta["slm_runtime_version"],
                audit_meta["slm_quantization"],
                int(audit_meta["slm_decoding_seed"]),
                audit_meta["payload_signature"],
                audit_meta["signature_key_id"],
                datetime.now(tz=UTC),
            )

    async def get(self, tenant_id: str, policy_id: str, version: str | None = None) -> dict[str, Any] | None:
        async with self._db.acquire(tenant_id) as conn:
            if version is None:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM collection_policies
                    WHERE tenant_id = $1 AND policy_id = $2
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    tenant_id,
                    policy_id,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM collection_policies
                    WHERE tenant_id = $1 AND policy_id = $2 AND version = $3
                    """,
                    tenant_id,
                    policy_id,
                    version,
                )
            return _row_to_policy(row) if row else None

    async def list_versions(self, tenant_id: str, policy_id: str, limit: int = 50) -> list[dict[str, Any]]:
        async with self._db.acquire(tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM collection_policies
                WHERE tenant_id = $1 AND policy_id = $2
                ORDER BY created_at DESC LIMIT $3
                """,
                tenant_id,
                policy_id,
                limit,
            )
            return [_row_to_policy(r) for r in rows]

    async def find_by_finding(self, tenant_id: str, finding_id: str) -> dict[str, Any] | None:
        async with self._db.acquire(tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM collection_policies
                WHERE tenant_id = $1
                  AND originating_finding @> jsonb_build_object('finding_id', $2::text)
                ORDER BY created_at DESC LIMIT 1
                """,
                tenant_id,
                finding_id,
            )
            return _row_to_policy(row) if row else None

    async def find_active_for_vehicle(self, tenant_id: str, vehicle_id: str) -> dict[str, Any] | None:
        async with self._db.acquire(tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT cp.*
                FROM collection_policies cp
                JOIN deployment_targets dt
                  ON dt.tenant_id = cp.tenant_id
                 AND dt.policy_id = cp.policy_id
                 AND dt.version = cp.version
                WHERE cp.tenant_id = $1
                  AND cp.vehicle_scope @> jsonb_build_array($2::text)
                  AND dt.status = 'accepted'
                ORDER BY cp.created_at DESC LIMIT 1
                """,
                tenant_id,
                vehicle_id,
            )
            return _row_to_policy(row) if row else None


class DeploymentRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def insert(self, tenant_id: str, record: dict[str, Any]) -> None:
        async with self._db.acquire(tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO deployment_targets (
                  deployment_id, tenant_id, policy_id, version, environment,
                  vehicle_scope, status, downstream_response, requested_at,
                  accepted_at, expires_at
                ) VALUES (
                  $1,$2,$3,$4,$5,$6::jsonb,$7,$8::jsonb,$9,$10,$11
                )
                """,
                record["deployment_id"],
                tenant_id,
                record["policy_id"],
                record["version"],
                record.get("environment", "dev"),
                json.dumps(record["vehicle_scope"]),
                record["status"],
                json.dumps(record.get("downstream_response", {})),
                datetime.now(tz=UTC),
                _parse_iso(record.get("deployed_at")),
                _parse_iso(record.get("expires_at")),
            )

    async def list_due(self, now: datetime) -> list[dict[str, Any]]:
        async with self._db.acquire(_PUBLIC) as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM deployment_targets
                WHERE status = 'accepted' AND expires_at IS NOT NULL AND expires_at <= $1
                ORDER BY expires_at ASC LIMIT 100
                """,
                now,
            )
            return [dict(r) for r in rows]

    async def mark_expired(self, deployment_id: str) -> None:
        async with self._db.acquire(_PUBLIC) as conn:
            await conn.execute(
                "UPDATE deployment_targets SET status = 'expired' WHERE deployment_id = $1",
                deployment_id,
            )


class OutcomeRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def insert(self, tenant_id: str, outcome: dict[str, Any]) -> None:
        async with self._db.acquire(tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO policy_outcomes (
                  outcome_id, tenant_id, originating_finding, policy_id, version,
                  hypothesis_state, evaluated_at, evidence_summary,
                  signals_collected_count, data_quality_score
                ) VALUES (
                  $1,$2,$3::jsonb,$4,$5,$6,$7,$8::jsonb,$9,$10
                )
                """,
                outcome["outcome_id"],
                tenant_id,
                json.dumps(outcome["originating_finding"]),
                outcome["policy_id"],
                outcome["version"],
                outcome["hypothesis_state"],
                outcome["evaluated_at"],
                json.dumps(outcome.get("evidence_summary", {})),
                int(outcome.get("signals_collected_count", 0)),
                float(outcome.get("data_quality_score", 0.0)),
            )

    async def get_by_finding(self, tenant_id: str, finding_id: str) -> dict[str, Any] | None:
        async with self._db.acquire(tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM policy_outcomes
                WHERE tenant_id = $1
                  AND originating_finding @> jsonb_build_object('finding_id', $2::text)
                ORDER BY evaluated_at DESC LIMIT 1
                """,
                tenant_id,
                finding_id,
            )
            return _row_to_outcome(row) if row else None


_PUBLIC = "feature-001-default"  # placeholder until feature 002 wires real tenant context


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _row_to_policy(row: asyncpg.Record) -> dict[str, Any]:
    d = dict(row)
    for k in ("signal_spec", "trigger_conditions", "vehicle_scope", "data_governance_flags", "originating_finding"):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    if isinstance(d.get("payload_signature"), bytes):
        d["payload_signature"] = d["payload_signature"].hex()
    return {
        "policy_id": d["policy_id"],
        "version": d["version"],
        "signals": d["signal_spec"],
        "trigger_conditions": d["trigger_conditions"],
        "collection_window_hours": d["collection_window_hours_logical"],
        "hypothesis": d["hypothesis_statement"],
        "vehicle_scope": d["vehicle_scope"],
        "data_governance_flags": d["data_governance_flags"],
        "confidence_threshold": float(d["confidence_threshold"]),
        "generated_from_session_id": d["generated_from_session_id"],
        "originating_finding": d["originating_finding"],
        "prompt_template_version": d["prompt_template_version"],
        "slm_repo": d["slm_repo"],
        "slm_revision_sha": d["slm_revision_sha"],
        "slm_runtime": d["slm_runtime"],
        "slm_runtime_version": d["slm_runtime_version"],
        "slm_quantization": d["slm_quantization"],
        "slm_decoding_seed": int(d["slm_decoding_seed"]),
        "created_at": d["created_at"].isoformat() if isinstance(d.get("created_at"), datetime) else d.get("created_at"),
    }


def _row_to_outcome(row: asyncpg.Record) -> dict[str, Any]:
    d = dict(row)
    for k in ("originating_finding", "evidence_summary"):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return {
        "outcome_id": d["outcome_id"],
        "originating_finding": d["originating_finding"],
        "policy_ref": {
            "tenant_id": d["tenant_id"],
            "policy_id": d["policy_id"],
            "version": d["version"],
        },
        "hypothesis_state": d["hypothesis_state"],
        "evaluated_at": d["evaluated_at"].isoformat()
        if isinstance(d.get("evaluated_at"), datetime)
        else d.get("evaluated_at"),
        "signals_collected_count": int(d.get("signals_collected_count", 0)),
        "data_quality_score": float(d.get("data_quality_score", 0.0)),
        "evidence_summary": d["evidence_summary"],
    }
