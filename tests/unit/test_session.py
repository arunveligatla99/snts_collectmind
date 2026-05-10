"""T055: PolicyGenerationSession state object serialization round-trip."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def session_payload() -> dict[str, object]:
    return {
        "session_id": "session-001",
        "tenant_id": "feature-001-default",
        "originating_finding": {
            "tenant_id": "feature-001-default",
            "finding_id": "F-001",
            "schema_version": "1.0.0",
            "anomaly_type": "brake_wear_early_stage",
            "hypothesis_class": "brake_wear",
            "hypothesis_statement": "rotor temperature excursions",
            "candidate_signals": ["Vehicle.Powertrain.CombustionEngine.EngineOilTemperature"],
            "vehicle_scope": ["VIN-1"],
            "upstream_confidence": 0.78,
        },
        "execution_plan": ["generate", "validate", "deploy"],
        "retry_count": 0,
        "retry_budget": 3,
        "validation_errors": [],
        "generated_policy": None,
        "deployment_record": None,
        "outcome_record": None,
        "correlation_id": "corr-123",
        "started_at": "2026-05-09T14:00:00Z",
    }


def test_session_round_trips(session_payload: dict[str, object]) -> None:
    from collectmind.graph.session import PolicyGenerationSession

    session = PolicyGenerationSession.model_validate(session_payload)
    serialized = session.model_dump_json()
    revived = PolicyGenerationSession.model_validate(json.loads(serialized))
    assert revived == session


def test_retry_budget_enforced(session_payload: dict[str, object]) -> None:
    from collectmind.graph.session import PolicyGenerationSession

    session = PolicyGenerationSession.model_validate(session_payload)
    session.retry_count = session.retry_budget
    assert session.retry_budget_exhausted() is True


def test_session_id_required(session_payload: dict[str, object]) -> None:
    from collectmind.graph.session import PolicyGenerationSession

    session_payload["session_id"] = ""
    with pytest.raises(Exception):
        PolicyGenerationSession.model_validate(session_payload)
