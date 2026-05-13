"""Unit tests for DevDefaultPolicyClient (T134 coverage)."""

from __future__ import annotations

import json

import pytest

from collectmind.slm.client import GenerationRequest
from collectmind.slm.dev_default_client import (
    DevDefaultPolicyClient,
    _build_policy,
    _extract_finding_from_prompt,
)


def _prompt(
    *,
    finding_id: str = "F-001",
    tenant_id: str = "feature-001-default",
    vehicle_scope: list[str] | None = None,
    confidence: float = 0.78,
    session_id: str = "session-xyz",
    candidate_signals: list[str] | None = None,
) -> str:
    scope = vehicle_scope if vehicle_scope is not None else ["VIN-1", "VIN-2"]
    cand = candidate_signals if candidate_signals is not None else []
    return (
        f"Finding: {finding_id}\n"
        f"Tenant: {tenant_id}\n"
        f"Vehicle scope: {json.dumps(scope)}\n"
        f"Upstream confidence: {confidence}\n"
        f"Candidate signals (optional hints): {json.dumps(cand)}\n"
        f'Sets `generated_from_session_id` to `"{session_id}"`\n'
    )


def test_extract_finding_pulls_every_field() -> None:
    parsed = _extract_finding_from_prompt(
        _prompt(
            finding_id="F-extract",
            tenant_id="tenantX",
            vehicle_scope=["VIN-a", "VIN-b"],
            confidence=0.42,
            session_id="sess",
            candidate_signals=["Vehicle.Foo"],
        )
    )
    assert parsed["finding_id"] == "F-extract"
    assert parsed["tenant_id"] == "tenantX"
    assert parsed["vehicle_scope"] == ["VIN-a", "VIN-b"]
    assert parsed["confidence"] == pytest.approx(0.42)
    assert parsed["session_id"] == "sess"
    assert parsed["candidate_signals"] == ["Vehicle.Foo"]


def test_extract_finding_defaults_on_missing_fields() -> None:
    parsed = _extract_finding_from_prompt("(empty prompt)")
    assert parsed["finding_id"] == "F-default-001"
    assert parsed["tenant_id"]  # default from env or constant
    assert parsed["vehicle_scope"] == ["VIN-default-001"]
    assert parsed["confidence"] == pytest.approx(0.7)
    assert parsed["session_id"] == "session-default-001"
    assert parsed["candidate_signals"] == []


def test_extract_finding_malformed_confidence_falls_back() -> None:
    prompt = (
        "Finding: F-mal\n"
        "Tenant: T\n"
        'Vehicle scope: ["VIN-1"]\n'
        "Upstream confidence: not-a-number-but-this-pattern-wont-match\n"
    )
    # The regex demands [0-9.]+ so a non-numeric value is treated as missing
    # and the default 0.7 applies.
    parsed = _extract_finding_from_prompt(prompt)
    assert parsed["confidence"] == pytest.approx(0.7)


def test_extract_finding_malformed_vehicle_scope_falls_back() -> None:
    prompt = "Finding: F-mal\nTenant: T\nVehicle scope: [not, valid, json]\n"
    parsed = _extract_finding_from_prompt(prompt)
    assert parsed["vehicle_scope"] == ["VIN-default-001"]


def test_build_policy_uses_candidate_signals_when_provided() -> None:
    policy = _build_policy(_prompt(finding_id="F-c", candidate_signals=["Vehicle.Foo", "Vehicle.Bar"]))
    names = [s["vss_name"] for s in policy["signals"]]
    assert names == ["Vehicle.Foo", "Vehicle.Bar"]
    assert policy["policy_id"] == "policy-F-c"
    assert policy["version"] == "1.0.0"
    assert policy["collection_window_hours"] == 72
    assert policy["data_governance_flags"] == {"pii_consent": False, "has_pii_signal": False}


def test_build_policy_default_brake_signals_when_no_candidates() -> None:
    policy = _build_policy(_prompt(candidate_signals=[]))
    names = [s["vss_name"] for s in policy["signals"]]
    assert "Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear" in names


def test_build_policy_confidence_threshold_below_confidence() -> None:
    policy = _build_policy(_prompt(confidence=0.78))
    assert policy["confidence_threshold"] == pytest.approx(0.68)


def test_build_policy_confidence_threshold_clamped() -> None:
    # confidence 0.05 -> threshold 0.05 - 0.1 = -0.05 -> clamped to 0.0
    policy = _build_policy(_prompt(confidence=0.05))
    assert policy["confidence_threshold"] == 0.0
    # confidence 1.5 -> threshold 1.5 - 0.1 = 1.4 -> clamped to 1.0
    policy = _build_policy(_prompt(confidence=1.5))
    assert policy["confidence_threshold"] == 1.0


def test_runtime_info_is_dev_default_signature() -> None:
    client = DevDefaultPolicyClient()
    info = client.runtime_info()
    assert info.slm_repo == "dev/default"
    assert info.slm_revision_sha == "0" * 40
    assert info.slm_runtime == "stub"
    assert info.constrained_decoding_library == "none"


def test_warmup_is_a_noop() -> None:
    client = DevDefaultPolicyClient()
    # Must not raise.
    assert client.warmup() is None


def test_generate_accepts_dict_request() -> None:
    client = DevDefaultPolicyClient()
    response = client.generate(
        {"session_id": "s", "prompt_template_version": "v1.0.0", "prompt": _prompt(finding_id="F-d")}
    )
    assert response.policy["policy_id"] == "policy-F-d"
    assert response.runtime_info["slm_repo"] == "dev/default"
    assert response.usage == {"input_tokens": 0, "output_tokens": 0, "generation_latency_ms": 0}


def test_generate_accepts_generation_request_dataclass() -> None:
    client = DevDefaultPolicyClient()
    request = GenerationRequest(
        session_id="s2",
        prompt_template_version="v1.0.0",
        prompt=_prompt(finding_id="F-gr"),
        schema={},
        decoding={},
    )
    response = client.generate(request)
    assert response.policy["policy_id"] == "policy-F-gr"
