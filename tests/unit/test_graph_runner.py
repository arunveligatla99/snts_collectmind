"""Unit tests for graph/runner.py (T134). Covers GraphRunner happy + error paths."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from collectmind.graph.build import GraphRun
from collectmind.graph.runner import GraphRunner
from collectmind.graph.session import PolicyGenerationSession


def _session(retry_count: int = 0) -> PolicyGenerationSession:
    return PolicyGenerationSession(
        session_id="s1",
        tenant_id="t1",
        correlation_id="c1",
        originating_finding={
            "tenant_id": "t1",
            "finding_id": "F1",
            "schema_version": "1.0.0",
            "anomaly_type": "brake_wear_early_stage",
            "hypothesis_class": "brake_wear",
            "hypothesis_statement": "h",
            "candidate_signals": [],
            "vehicle_scope": ["VIN-1"],
            "upstream_confidence": 0.78,
        },
        retry_count=retry_count,
        started_at=datetime.now(tz=UTC),
    )


def _runtime_info() -> dict[str, Any]:
    return {
        "slm_repo": "Qwen/Qwen2.5-7B-Instruct",
        "slm_revision_sha": "a" * 40,
        "slm_runtime": "stub",
        "slm_runtime_version": "v1",
        "slm_quantization": "none",
    }


def _policy() -> dict[str, Any]:
    return {
        "policy_id": "p1",
        "version": "1.0.0",
        "signals": [],
        "vehicle_scope": ["VIN-1"],
    }


def _deployment_record(status: str = "accepted") -> dict[str, Any]:
    return {
        "deployment_id": "dep-1",
        "status": status,
        "tenant_id": "t1",
        "policy_id": "p1",
        "version": "1.0.0",
        "vehicle_scope": ["VIN-1"],
    }


def _build_runner(*, final_state: str = "completed", with_deployment: bool = True):  # type: ignore[no-untyped-def]
    """Construct a GraphRunner whose collaborators are all mocked.

    Returns (runner, audit_writer, telemetry, deployment_repo, policy_repo,
    signer, scheduler) for assertion inspection.
    """
    audit_writer = MagicMock()
    audit_writer.write = AsyncMock()
    policy_repo = MagicMock()
    policy_repo.insert = AsyncMock()
    deployment_repo = MagicMock()
    deployment_repo.insert = AsyncMock()
    telemetry = MagicMock()
    telemetry.simulate = AsyncMock()
    signer = MagicMock()
    signer.sign = MagicMock(return_value=(b"sig", "k1"))
    scheduler = MagicMock()
    scheduler.factor = 10000.0

    # Build a graph mock that returns a session populated with the desired fields.
    def _graph_run(session: PolicyGenerationSession):  # type: ignore[no-untyped-def]
        session.generated_policy = _policy()
        session.last_runtime_info = _runtime_info()
        session.last_decoding_seed = 1
        session.prompt_template_version = "v1"
        if with_deployment:
            session.deployment_record = _deployment_record()
        return GraphRun(session=session, final_state=final_state, validation_attempts=1)

    graph = MagicMock()
    graph.run = MagicMock(side_effect=_graph_run)

    runner = GraphRunner(
        graph=graph,
        policy_repo=policy_repo,
        deployment_repo=deployment_repo,
        audit_writer=audit_writer,
        telemetry_generator=telemetry,
        signer=signer,
        scheduler=scheduler,
    )
    return runner, audit_writer, telemetry, deployment_repo, policy_repo, signer


@pytest.mark.asyncio
async def test_happy_path_writes_generated_validated_deployed_audits() -> None:
    runner, audit, telemetry, dep_repo, pol_repo, signer = _build_runner()
    s = _session()
    await runner.run_async(s, sim_directive="confirm", accel_header=None)
    # Three writes minimum: generated, validated, deployed.
    kinds = [c.kwargs["kind"] for c in audit.write.await_args_list]
    assert "generated" in kinds
    assert "validated" in kinds
    assert "deployed" in kinds
    pol_repo.insert.assert_awaited()
    dep_repo.insert.assert_awaited()
    telemetry.simulate.assert_awaited()
    signer.sign.assert_called_once()


@pytest.mark.asyncio
async def test_dead_letter_path_writes_rejected_audit() -> None:
    runner, audit, telemetry, _dep, _pol, _sign = _build_runner(final_state="dead_letter", with_deployment=False)
    s = _session()
    # Inject validation_errors so the rejected audit row has shape.
    s.validation_errors = [{"code": "VSS_INVALID_SIGNAL", "field": "signals", "details": {"invalid_signals": ["X"]}}]
    # Force run to mark dead_letter and skip deployment.
    await runner.run_async(s)
    kinds = [c.kwargs["kind"] for c in audit.write.await_args_list]
    assert "rejected" in kinds
    telemetry.simulate.assert_not_awaited()


@pytest.mark.asyncio
async def test_exception_in_graph_yields_rejected_audit() -> None:
    audit_writer = MagicMock()
    audit_writer.write = AsyncMock()
    policy_repo = MagicMock()
    deployment_repo = MagicMock()
    telemetry = MagicMock()
    signer = MagicMock()
    scheduler = MagicMock()
    scheduler.factor = 1.0

    graph = MagicMock()
    graph.run = MagicMock(side_effect=RuntimeError("kaboom"))
    runner = GraphRunner(
        graph=graph,
        policy_repo=policy_repo,
        deployment_repo=deployment_repo,
        audit_writer=audit_writer,
        telemetry_generator=telemetry,
        signer=signer,
        scheduler=scheduler,
    )
    s = _session()
    await runner.run_async(s)
    # On exception the runner writes a single rejected audit row with the error.
    kinds = [c.kwargs["kind"] for c in audit_writer.write.await_args_list]
    assert kinds == ["rejected"]


@pytest.mark.asyncio
async def test_no_deployment_record_skips_dep_repo_and_telemetry() -> None:
    runner, _audit, telemetry, dep_repo, _pol, _sign = _build_runner(final_state="completed", with_deployment=False)
    s = _session()
    await runner.run_async(s)
    dep_repo.insert.assert_not_awaited()
    telemetry.simulate.assert_not_awaited()
