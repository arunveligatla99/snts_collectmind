"""T052: AsyncAPI conformance for diagnostic-findings, vehicle-telemetry,
policy-deployments, and policy-outcomes (4 topics) using the harness from T043.
"""

from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest
import yaml

from tests.contract.asyncapi_harness import load_message_schema, validate_message

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts" / "asyncapi"


def _load(channel: str) -> dict[str, object]:
    for path in CONTRACTS_DIR.glob("*.yaml"):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if channel in doc.get("channels", {}):
            return doc
    raise AssertionError(f"channel {channel!r} not found in {CONTRACTS_DIR}")


@pytest.mark.parametrize(
    "channel,message_name",
    [
        ("diagnostic-findings.v1", "DiagnosticFindingMessage"),
        ("vehicle-telemetry.v1", "TelemetryObservationMessage"),
        ("policy-deployments.v1", "PolicyDeploymentMessage"),
        ("policy-outcomes.v1", "PolicyOutcomeMessage"),
    ],
)
def test_channel_present_with_payload_schema(channel: str, message_name: str) -> None:
    schema = load_message_schema(channel, message_name)
    assert "type" in schema or "$ref" in schema, f"empty schema for {channel}:{message_name}"


def test_diagnostic_finding_message_validates() -> None:
    instance = {
        "finding_id": "F-001",
        "anomaly_type": "brake_wear_early_stage",
        "hypothesis_class": "brake_wear",
        "hypothesis_statement": "rotor temperature excursions correlated with mileage.",
        "candidate_signals": ["Vehicle.Powertrain.CombustionEngine.EngineOilTemperature"],
        "vehicle_scope": ["VIN-1"],
        "upstream_confidence": 0.78,
    }
    validate_message("diagnostic-findings.v1", "DiagnosticFindingMessage", instance)


def test_telemetry_observation_validates() -> None:
    instance = {
        "vehicle_id": "VIN-1",
        "signal_name": "Vehicle.Speed",
        "value": 42.5,
        "observed_at": "2026-05-09T14:00:00Z",
        "source": "simulator",
    }
    validate_message("vehicle-telemetry.v1", "TelemetryObservationMessage", instance)


def test_policy_deployment_validates() -> None:
    instance = {
        "deployment_id": "D-001",
        "policy_id": "P-001",
        "version": "1.0.0",
        "vehicle_scope": ["VIN-1"],
        "status": "accepted",
        "deployed_at": "2026-05-09T14:00:00Z",
        "expires_at": "2026-05-12T14:00:00Z",
    }
    validate_message("policy-deployments.v1", "PolicyDeploymentMessage", instance)


def test_policy_outcome_validates() -> None:
    instance = {
        "outcome_id": "O-001",
        "originating_finding": {"tenant_id": "feature-001-default", "finding_id": "F-001"},
        "hypothesis_state": "confirmed",
        "evaluated_at": "2026-05-12T14:00:00Z",
    }
    validate_message("policy-outcomes.v1", "PolicyOutcomeMessage", instance)


def test_invalid_diagnostic_finding_rejected() -> None:
    """Negative path: missing required field is rejected."""
    instance = {
        "finding_id": "F-001",
        "anomaly_type": "brake_wear_early_stage",
        # hypothesis_class deliberately missing
        "hypothesis_statement": "x",
        "candidate_signals": ["Vehicle.Speed"],
        "vehicle_scope": ["VIN-1"],
        "upstream_confidence": 0.5,
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_message("diagnostic-findings.v1", "DiagnosticFindingMessage", instance)
