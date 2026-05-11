"""GraphRunner: persist + audit between graph nodes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog

from collectmind.deployer.signing import LocalKeySigner
from collectmind.feedback.scheduler import LogicalTimeScheduler
from collectmind.graph.build import CollectMindGraph
from collectmind.graph.session import PolicyGenerationSession
from collectmind.observability.metrics import (
    policy_deployed_total,
    policy_generated_total,
    policy_validated_total,
    slm_runtime_image_digest_active,
    slm_weight_sha_active,
    time_to_deploy_seconds,
)
from collectmind.registry.audit import AuditEventWriter
from collectmind.registry.repository import DeploymentRepository, PolicyRepository
from collectmind.simulators.telemetry_generator import TelemetryGenerator

logger = structlog.get_logger(__name__)


class GraphRunner:
    def __init__(
        self,
        graph: CollectMindGraph,
        policy_repo: PolicyRepository,
        deployment_repo: DeploymentRepository,
        audit_writer: AuditEventWriter,
        telemetry_generator: TelemetryGenerator,
        signer: LocalKeySigner,
        scheduler: LogicalTimeScheduler,
    ) -> None:
        self._graph = graph
        self._policy_repo = policy_repo
        self._deployment_repo = deployment_repo
        self._audit_writer = audit_writer
        self._telemetry_generator = telemetry_generator
        self._signer = signer
        self._scheduler = scheduler

    async def run_async(
        self,
        session: PolicyGenerationSession,
        *,
        sim_directive: str | None = None,
        accel_header: str | None = None,
    ) -> None:
        try:
            await self._run(session, sim_directive=sim_directive, accel_header=accel_header)
        except Exception as exc:
            logger.error("graph_runner_error", error=str(exc), correlation_id=session.correlation_id)
            await self._audit_writer.write(
                tenant_id=session.tenant_id,
                kind="rejected",
                correlation_id=session.correlation_id,
                principal_subject=session.session_id,
                originating_finding=_finding_ref(session),
                error={"code": "GRAPH_RUNNER_ERROR", "message": str(exc)},
            )

    async def _run(
        self,
        session: PolicyGenerationSession,
        *,
        sim_directive: str | None,
        accel_header: str | None,
    ) -> None:
        start = datetime.now(tz=UTC)
        loop = asyncio.get_running_loop()
        run = await loop.run_in_executor(None, self._graph.run, session)
        session = run.session

        runtime_info = session.last_runtime_info or {}
        slm_weight_sha_active.labels(sha=runtime_info.get("slm_revision_sha", "unknown")).set(1)
        slm_runtime_image_digest_active.labels(
            digest=runtime_info.get("slm_runtime_version", "unknown"),
            runtime=runtime_info.get("slm_runtime", "unknown"),
        ).set(1)

        if session.generated_policy is not None:
            policy_generated_total.labels(tenant_id=session.tenant_id).inc()
            await self._audit_writer.write(
                tenant_id=session.tenant_id,
                kind="generated",
                correlation_id=session.correlation_id,
                principal_subject=session.session_id,
                originating_finding=_finding_ref(session),
                policy_ref={
                    "tenant_id": session.tenant_id,
                    "policy_id": session.generated_policy["policy_id"],
                    "version": session.generated_policy["version"],
                },
                slm_repo=runtime_info.get("slm_repo"),
                slm_revision_sha=runtime_info.get("slm_revision_sha"),
                slm_runtime=runtime_info.get("slm_runtime"),
                slm_runtime_version=runtime_info.get("slm_runtime_version"),
                slm_quantization=runtime_info.get("slm_quantization"),
                slm_decoding_seed=session.last_decoding_seed,
                prompt_template_version=session.prompt_template_version,
                inbound_schema_version=session.originating_finding.get("schema_version"),
                time_acceleration_factor=self._scheduler.factor,
            )

        if run.final_state == "dead_letter":
            await self._audit_writer.write(
                tenant_id=session.tenant_id,
                kind="rejected",
                correlation_id=session.correlation_id,
                principal_subject=session.session_id,
                originating_finding=_finding_ref(session),
                error={
                    "code": "VALIDATION_FAILED",
                    "details": {
                        "validation_errors": session.validation_errors,
                        "invalid_signals": _flatten_invalid(session.validation_errors),
                    },
                },
                inbound_schema_version=session.originating_finding.get("schema_version"),
            )
            return

        # Policy validated and deployed; persist registry rows.
        signature, key_id = self._signer.sign(session.generated_policy or {})
        audit_meta = {
            "prompt_template_version": session.prompt_template_version,
            "slm_repo": runtime_info.get("slm_repo", "unknown"),
            "slm_revision_sha": runtime_info.get("slm_revision_sha", "0" * 40),
            "slm_runtime": runtime_info.get("slm_runtime", "stub"),
            "slm_runtime_version": runtime_info.get("slm_runtime_version", "unknown"),
            "slm_quantization": runtime_info.get("slm_quantization", "none"),
            "slm_decoding_seed": session.last_decoding_seed or 0,
            "payload_signature": signature,
            "signature_key_id": key_id,
        }
        await self._policy_repo.insert(session.tenant_id, session.generated_policy or {}, audit_meta)
        policy_validated_total.labels(tenant_id=session.tenant_id).inc()
        await self._audit_writer.write(
            tenant_id=session.tenant_id,
            kind="validated",
            correlation_id=session.correlation_id,
            principal_subject=session.session_id,
            originating_finding=_finding_ref(session),
            policy_ref={
                "tenant_id": session.tenant_id,
                "policy_id": _policy_field(session.generated_policy, "policy_id"),
                "version": _policy_field(session.generated_policy, "version"),
            },
        )

        deployment = session.deployment_record or {}
        if deployment:
            await self._deployment_repo.insert(session.tenant_id, deployment)
            policy_deployed_total.labels(tenant_id=session.tenant_id).inc()
            await self._audit_writer.write(
                tenant_id=session.tenant_id,
                kind="deployed",
                correlation_id=session.correlation_id,
                principal_subject=session.session_id,
                originating_finding=_finding_ref(session),
                policy_ref={
                    "tenant_id": session.tenant_id,
                    "policy_id": _policy_field(session.generated_policy, "policy_id"),
                    "version": _policy_field(session.generated_policy, "version"),
                },
                deployment_ref={"deployment_id": deployment.get("deployment_id")},
                time_acceleration_factor=self._scheduler.factor,
            )
            elapsed = (datetime.now(tz=UTC) - start).total_seconds()
            time_to_deploy_seconds.labels(tenant_id=session.tenant_id).observe(elapsed)

            await self._telemetry_generator.simulate(
                tenant_id=session.tenant_id,
                policy=session.generated_policy or {},
                deployment_id=deployment.get("deployment_id", ""),
                directive=sim_directive,
            )


def _policy_field(policy: dict[str, object] | None, key: str) -> str:
    if policy is None:
        return ""
    value = policy.get(key)
    return str(value) if value is not None else ""


def _finding_ref(session: PolicyGenerationSession) -> dict[str, str]:
    return {
        "tenant_id": session.tenant_id,
        "finding_id": session.originating_finding.get("finding_id", ""),
    }


def _flatten_invalid(errors: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for err in errors:
        details = err.get("details") or {}
        out.extend(details.get("invalid_signals", []))
    return out
