"""FeedbackWorker (T093). Polls expired deployments, evaluates, writes outcome."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import ulid

from collectmind.feedback.evaluator import BrakeWearHypothesisRule, HypothesisOutcome
from collectmind.feedback.scheduler import LogicalTimeScheduler
from collectmind.observability.logging import get_logger
from collectmind.observability.metrics import policy_outcome_total
from collectmind.registry.audit import AuditEventWriter
from collectmind.registry.db import Database
from collectmind.registry.repository import DeploymentRepository, OutcomeRepository, PolicyRepository


logger = get_logger(__name__)


class FeedbackWorker:
    def __init__(
        self,
        db: Database,
        deployment_repo: DeploymentRepository,
        policy_repo: PolicyRepository,
        outcome_repo: OutcomeRepository,
        audit_writer: AuditEventWriter,
        rule: BrakeWearHypothesisRule | None = None,
        scheduler: LogicalTimeScheduler | None = None,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._db = db
        self._deployment_repo = deployment_repo
        self._policy_repo = policy_repo
        self._outcome_repo = outcome_repo
        self._audit_writer = audit_writer
        self._rule = rule or BrakeWearHypothesisRule()
        self._scheduler = scheduler or LogicalTimeScheduler()
        self._poll_interval = poll_interval_seconds
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    async def run_forever(self) -> None:
        while not self._stopped:
            try:
                await self.tick()
            except Exception as exc:  # noqa: BLE001
                logger.error("feedback_tick_error", error=str(exc))
            await asyncio.sleep(self._poll_interval)

    async def tick(self) -> int:
        now = self._scheduler.now()
        due = await self._deployment_repo.list_due(now)
        for record in due:
            await self._process(record)
        return len(due)

    async def _process(self, deployment: dict[str, Any]) -> None:
        tenant_id = deployment["tenant_id"]
        policy_id = deployment["policy_id"]
        version = deployment["version"]
        deployment_id = deployment["deployment_id"]
        vehicle_scope_raw = deployment["vehicle_scope"]
        vehicle_scope = json.loads(vehicle_scope_raw) if isinstance(vehicle_scope_raw, str) else list(vehicle_scope_raw)

        policy = await self._policy_repo.get(tenant_id, policy_id, version)
        if policy is None:
            await self._deployment_repo.mark_expired(deployment_id)
            return

        observations = await self._collect_telemetry(tenant_id, vehicle_scope, deployment)
        outcome: HypothesisOutcome = self._rule.evaluate(
            observations=observations,
            expected_threshold=float(policy.get("confidence_threshold", 0.5)),
        )

        outcome_record = {
            "outcome_id": str(ulid.new()),
            "originating_finding": policy["originating_finding"],
            "policy_id": policy_id,
            "version": version,
            "hypothesis_state": outcome.hypothesis_state,
            "evaluated_at": datetime.now(tz=timezone.utc),
            "signals_collected_count": outcome.signals_collected_count,
            "data_quality_score": outcome.data_quality_score,
            "evidence_summary": outcome.evidence_summary,
        }
        await self._outcome_repo.insert(tenant_id, outcome_record)
        await self._deployment_repo.mark_expired(deployment_id)
        policy_outcome_total.labels(tenant_id=tenant_id, state=outcome.hypothesis_state).inc()

        await self._audit_writer.write(
            tenant_id=tenant_id,
            kind="outcome",
            correlation_id=deployment.get("correlation_id", deployment_id),
            principal_subject="feedback-worker",
            originating_finding=policy["originating_finding"],
            policy_ref={"tenant_id": tenant_id, "policy_id": policy_id, "version": version},
            outcome_ref={"outcome_id": outcome_record["outcome_id"]},
            time_acceleration_factor=self._scheduler.factor,
        )

    async def _collect_telemetry(
        self,
        tenant_id: str,
        vehicle_scope: list[str],
        deployment: dict[str, Any],
    ) -> list[dict[str, Any]]:
        async with self._db.acquire(tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT vehicle_id, signal_name, value, observed_at
                FROM telemetry_observations
                WHERE tenant_id = $1
                  AND vehicle_id = ANY($2::text[])
                  AND policy_ref @> jsonb_build_object('policy_id', $3::text, 'version', $4::text)
                ORDER BY observed_at DESC LIMIT 1000
                """,
                tenant_id,
                vehicle_scope,
                deployment.get("policy_id", ""),
                deployment.get("version", ""),
            )
        return [dict(r) for r in rows]
