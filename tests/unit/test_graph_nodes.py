"""Unit tests for the four LangGraph nodes + CollectMindGraph composer (T134)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from collectmind.deployer.client import DeployResponse
from collectmind.graph.build import CollectMindGraph
from collectmind.graph.orchestrator import Orchestrator
from collectmind.graph.policy_deployer import PolicyDeployer
from collectmind.graph.policy_generator import PolicyGenerator
from collectmind.graph.policy_validator import PolicyValidatorNode
from collectmind.graph.session import PolicyGenerationSession
from collectmind.slm.client import GenerationResponse
from collectmind.slm.dev_default_client import DevDefaultPolicyClient
from collectmind.validator.policy_validator import ValidationError, ValidationResult


def _session(retry_count: int = 0) -> PolicyGenerationSession:
    return PolicyGenerationSession(
        session_id="s1",
        tenant_id="t1",
        correlation_id="c1",
        originating_finding={
            "tenant_id": "t1",
            "finding_id": "F1",
            "anomaly_type": "brake_wear_early_stage",
            "hypothesis_class": "brake_wear",
            "hypothesis_statement": "x",
            "vehicle_scope": ["VIN-1"],
            "candidate_signals": [],
            "upstream_confidence": 0.78,
        },
        retry_count=retry_count,
        started_at=datetime.now(tz=UTC),
    )


class TestOrchestrator:
    def test_initial_plan_sets_three_steps(self) -> None:
        orch = Orchestrator()
        s = orch.initial_plan(_session())
        assert s.execution_plan == ["generate", "validate", "deploy"]

    def test_route_after_validation_deploys_on_valid(self) -> None:
        assert Orchestrator().route_after_validation(_session(), valid=True) == "deploy"

    def test_route_after_validation_dead_letter_on_exhausted_retry(self) -> None:
        s = _session(retry_count=3)
        assert Orchestrator().route_after_validation(s, valid=False) == "dead_letter"

    def test_route_after_validation_retries_when_budget_available(self) -> None:
        s = _session(retry_count=0)
        result = Orchestrator().route_after_validation(s, valid=False)
        assert result == "retry"
        assert s.retry_count == 1  # incremented on retry path

    def test_route_after_deploy(self) -> None:
        assert Orchestrator().route_after_deploy(True) == "done"
        assert Orchestrator().route_after_deploy(False) == "dead_letter"


class TestPolicyGenerator:
    def test_generate_sets_session_state(self) -> None:
        client = DevDefaultPolicyClient()
        generator = PolicyGenerator(client)
        s = _session()
        policy = generator.generate(s)
        assert s.generated_policy is not None
        assert s.last_runtime_info is not None
        assert s.last_decoding_seed == 0xC0FFEE
        assert policy["policy_id"].startswith("policy-")

    def test_generate_uses_retry_context_on_subsequent_attempt(self) -> None:
        captured: dict[str, Any] = {}

        class _SpyClient:
            def generate(self, request: Any) -> GenerationResponse:
                captured["request"] = request.to_dict() if hasattr(request, "to_dict") else dict(request)
                return GenerationResponse(
                    policy={
                        "policy_id": "p-spy",
                        "version": "1.0.0",
                        "signals": [],
                        "trigger_conditions": [],
                        "collection_window_hours": 1,
                        "hypothesis": "h",
                        "vehicle_scope": ["VIN-1"],
                        "data_governance_flags": {"pii_consent": False, "has_pii_signal": False},
                        "confidence_threshold": 0.5,
                        "generated_from_session_id": "s",
                        "originating_finding": {"tenant_id": "t1", "finding_id": "F1"},
                    },
                    runtime_info={
                        "slm_repo": "x",
                        "slm_revision_sha": "0" * 40,
                        "slm_runtime": "stub",
                        "slm_runtime_version": "v",
                        "slm_quantization": "n",
                        "constrained_decoding_library": "none",
                        "constraint_violation_count": 0,
                    },
                )

            def warmup(self) -> None:
                return None

            def runtime_info(self) -> Any:
                return None

        s = _session()
        s.validation_errors = [{"code": "VSS_INVALID_SIGNAL", "field": "signals", "message": "x", "details": {}}]
        PolicyGenerator(_SpyClient()).generate(s)
        # retry_context flows into the GenerationRequest
        assert captured["request"]["retry_context"] is not None
        assert captured["request"]["retry_context"]["validation_errors"][0]["code"] == "VSS_INVALID_SIGNAL"


class TestPolicyValidatorNode:
    def test_raises_when_no_generated_policy(self) -> None:
        with pytest.raises(RuntimeError, match="before generator"):
            PolicyValidatorNode().validate(_session())

    def test_schema_invalid_policy_marks_validation_error(self) -> None:
        s = _session()
        s.generated_policy = {"not": "a-policy"}
        node = PolicyValidatorNode(validator=MagicMock())
        result = node.validate(s)
        assert result.ok is False
        assert s.validation_errors
        assert s.validation_errors[0]["code"] == "SCHEMA_VALIDATION_FAILED"

    def test_valid_policy_clears_validation_errors(self) -> None:
        s = _session()
        # Build a minimal schema-valid policy
        s.generated_policy = _valid_policy()
        s.validation_errors = [{"code": "stale", "field": "x", "message": "y"}]
        node = PolicyValidatorNode(validator=_FakeOkValidator())
        result = node.validate(s)
        assert result.ok is True
        assert s.validation_errors == []

    def test_validator_failure_populates_session_errors(self) -> None:
        s = _session()
        s.generated_policy = _valid_policy()
        validator = _FakeFailValidator(
            errors=[ValidationError(code="VSS_INVALID_SIGNAL", field="signals", message="m", details={})]
        )
        result = PolicyValidatorNode(validator=validator).validate(s)
        assert result.ok is False
        assert s.validation_errors[0]["code"] == "VSS_INVALID_SIGNAL"


class TestPolicyDeployer:
    def test_deploy_creates_record_and_signs(self) -> None:
        signer = MagicMock()
        signer.sign = MagicMock(return_value=("sig-hex", "key-id-1"))
        client = MagicMock()
        client.deploy = MagicMock(
            return_value=DeployResponse(
                deployment_id="dep-1",
                status="accepted",
                downstream_response={"ok": True},
                expires_at="2026-05-12T00:00:00+00:00",
            )
        )
        s = _session()
        s.generated_policy = _valid_policy()
        record = PolicyDeployer(client, signer).deploy(s)
        assert record["status"] == "accepted"
        assert record["deployment_id"] == "dep-1"
        signer.sign.assert_called_once()
        client.deploy.assert_called_once()


class TestCollectMindGraph:
    def test_happy_path_completes(self) -> None:
        s = _session()
        # Pre-bake a valid policy by stubbing the generator
        generator = _FakeGenerator(_valid_policy())
        validator = PolicyValidatorNode(validator=_FakeOkValidator())
        deployer = _FakeDeployer(status="accepted")
        graph = CollectMindGraph(generator=generator, validator=validator, deployer=deployer)
        run = graph.run(s)
        assert run.final_state == "completed"
        assert run.validation_attempts == 1
        assert s.generated_policy is not None
        assert s.deployment_record is not None

    def test_dead_letter_on_repeated_validation_failure(self) -> None:
        s = _session()
        # Validator always fails; orchestrator hits retry_budget (3) and dead-letters.
        generator = _FakeGenerator(_valid_policy())
        validator = PolicyValidatorNode(
            validator=_FakeFailValidator(
                errors=[ValidationError(code="VSS_INVALID_SIGNAL", field="signals", message="m")]
            )
        )
        deployer = _FakeDeployer(status="accepted")
        graph = CollectMindGraph(generator=generator, validator=validator, deployer=deployer)
        run = graph.run(s)
        assert run.final_state == "dead_letter"

    def test_dead_letter_on_deploy_failure(self) -> None:
        s = _session()
        generator = _FakeGenerator(_valid_policy())
        validator = PolicyValidatorNode(validator=_FakeOkValidator())
        deployer = _FakeDeployer(status="rejected")
        run = CollectMindGraph(generator=generator, validator=validator, deployer=deployer).run(s)
        assert run.final_state == "dead_letter"


# --- helpers ----------------------------------------------------------------


def _valid_policy() -> dict[str, Any]:
    return {
        "policy_id": "p-valid",
        "version": "1.0.0",
        "signals": [
            {
                "vss_name": "Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear",
                "sample_rate_hz": 1.0,
                "priority": 5,
            }
        ],
        "trigger_conditions": [{"kind": "time_window", "params": {"window_hours": 72}}],
        "collection_window_hours": 72,
        "hypothesis": "h",
        "vehicle_scope": ["VIN-1"],
        "data_governance_flags": {"pii_consent": False, "has_pii_signal": False},
        "confidence_threshold": 0.5,
        "generated_from_session_id": "s",
        "originating_finding": {"tenant_id": "t1", "finding_id": "F1"},
    }


class _FakeGenerator:
    def __init__(self, policy: dict[str, Any]) -> None:
        self._policy = policy

    def generate(self, session: PolicyGenerationSession) -> dict[str, Any]:
        session.generated_policy = self._policy
        session.last_runtime_info = {
            "slm_repo": "x",
            "slm_revision_sha": "0" * 40,
            "slm_runtime": "stub",
        }
        session.last_decoding_seed = 1
        return self._policy


class _FakeOkValidator:
    def validate(self, _policy: Any) -> ValidationResult:
        return ValidationResult(ok=True, errors=[])


class _FakeFailValidator:
    def __init__(self, errors: list[ValidationError]) -> None:
        self._errors = errors

    def validate(self, _policy: Any) -> ValidationResult:
        return ValidationResult(ok=False, errors=self._errors)


class _FakeDeployer:
    def __init__(self, status: str) -> None:
        self._status = status

    def deploy(self, session: PolicyGenerationSession) -> dict[str, Any]:
        record = {"deployment_id": "dep-1", "status": self._status}
        session.deployment_record = record
        return record
