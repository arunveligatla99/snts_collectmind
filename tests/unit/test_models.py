"""T054: Pydantic v2 invariants on CollectionPolicySpec.

Covers: required fields; window 1..168; semver patterns; signal_spec non-empty;
data_governance_flags shape.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def valid_payload() -> dict[str, object]:
    return {
        "policy_id": "policy-1",
        "version": "1.0.0",
        "signals": [
            {"vss_name": "Vehicle.Speed", "sample_rate_hz": 10.0, "priority": 5},
        ],
        "trigger_conditions": [
            {"kind": "threshold", "params": {"signal": "Vehicle.Speed", "op": ">", "value": 100}},
        ],
        "collection_window_hours": 24,
        "hypothesis": "rotor temperature excursion correlation",
        "vehicle_scope": ["VIN-1"],
        "data_governance_flags": {"pii_consent": False, "has_pii_signal": False},
        "confidence_threshold": 0.8,
        "generated_from_session_id": "session-1",
        "originating_finding": {"tenant_id": "feature-001-default", "finding_id": "F-001"},
    }


def test_valid_payload_constructs(valid_payload: dict[str, object]) -> None:
    from collectmind.models.policy import CollectionPolicySpec

    spec = CollectionPolicySpec.model_validate(valid_payload)
    assert spec.collection_window_hours == 24
    assert len(spec.signals) == 1


@pytest.mark.parametrize("hours", [0, 169, 1000, -1])
def test_window_bounds_rejected(valid_payload, hours: int) -> None:
    from collectmind.models.policy import CollectionPolicySpec

    valid_payload["collection_window_hours"] = hours
    with pytest.raises(Exception):  # Pydantic ValidationError
        CollectionPolicySpec.model_validate(valid_payload)


@pytest.mark.parametrize("hours", [1, 24, 72, 168])
def test_window_bounds_accepted(valid_payload, hours: int) -> None:
    from collectmind.models.policy import CollectionPolicySpec

    valid_payload["collection_window_hours"] = hours
    spec = CollectionPolicySpec.model_validate(valid_payload)
    assert spec.collection_window_hours == hours


@pytest.mark.parametrize("version", ["1.0", "v1.0.0", "1.0.0-alpha", "abc"])
def test_invalid_semver_rejected(valid_payload, version: str) -> None:
    from collectmind.models.policy import CollectionPolicySpec

    valid_payload["version"] = version
    with pytest.raises(Exception):
        CollectionPolicySpec.model_validate(valid_payload)


def test_empty_signals_rejected(valid_payload) -> None:
    from collectmind.models.policy import CollectionPolicySpec

    valid_payload["signals"] = []
    with pytest.raises(Exception):
        CollectionPolicySpec.model_validate(valid_payload)


def test_pii_consent_required_when_has_pii(valid_payload) -> None:
    from collectmind.models.policy import CollectionPolicySpec

    valid_payload["data_governance_flags"] = {"pii_consent": False, "has_pii_signal": True}
    with pytest.raises(Exception):
        CollectionPolicySpec.model_validate(valid_payload)


def test_confidence_threshold_bounds(valid_payload) -> None:
    from collectmind.models.policy import CollectionPolicySpec

    for bad in [-0.01, 1.01, 2.0]:
        valid_payload["confidence_threshold"] = bad
        with pytest.raises(Exception):
            CollectionPolicySpec.model_validate(valid_payload)


def test_originating_finding_carries_composite_key(valid_payload) -> None:
    from collectmind.models.policy import CollectionPolicySpec

    valid_payload["originating_finding"] = {"tenant_id": "", "finding_id": "F-001"}
    with pytest.raises(Exception):
        CollectionPolicySpec.model_validate(valid_payload)
