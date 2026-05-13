"""Unit tests for PolicyValidator orchestration (T134)."""

from __future__ import annotations

from unittest.mock import MagicMock

from collectmind.models.policy import (
    CollectionPolicySpec,
    DataGovernanceFlags,
    SignalCollectionSpec,
    TriggerSpec,
)
from collectmind.validator.governance import GovernanceDecision
from collectmind.validator.policy_validator import PolicyValidator, ValidationError, ValidationResult
from collectmind.validator.vss import SignalValidationResult


def _spec(
    *,
    signals: list[SignalCollectionSpec] | None = None,
    window: int = 72,
    pii_consent: bool = False,
    has_pii_signal: bool = False,
) -> CollectionPolicySpec:
    return CollectionPolicySpec(
        policy_id="p1",
        version="1.0.0",
        signals=signals
        or [
            SignalCollectionSpec(
                vss_name="Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear",
                sample_rate_hz=1.0,
                priority=5,
            )
        ],
        trigger_conditions=[TriggerSpec(kind="time_window", params={"window_hours": window})],
        collection_window_hours=window,
        hypothesis="h",
        vehicle_scope=["VIN-1"],
        data_governance_flags=DataGovernanceFlags(pii_consent=pii_consent, has_pii_signal=has_pii_signal),
        confidence_threshold=0.5,
        generated_from_session_id="s",
        originating_finding={"tenant_id": "t", "finding_id": "F1"},
    )


def _validator(
    *,
    vss_ok: bool = True,
    suggestion: str | None = None,
    governance: GovernanceDecision | None = None,
) -> PolicyValidator:
    vss = MagicMock()
    vss.validate_signal = MagicMock(
        side_effect=lambda name: SignalValidationResult(name=name, ok=vss_ok, suggestion=suggestion)
    )
    gov = MagicMock()
    gov.evaluate_signals = MagicMock(return_value=governance or GovernanceDecision(ok=True))
    return PolicyValidator(vss=vss, governance=gov)


def test_ok_when_signals_valid_and_no_pii() -> None:
    result = _validator().validate(_spec())
    assert result.ok is True
    assert result.errors == []


def test_vss_invalid_signal_collected_into_errors() -> None:
    result = _validator(vss_ok=False, suggestion="closest.match").validate(_spec())
    assert result.ok is False
    assert any(e.code == "VSS_INVALID_SIGNAL" for e in result.errors)
    assert result.suggestions["Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear"] == "closest.match"


def test_pii_consent_required_when_governance_rejects() -> None:
    decision = GovernanceDecision(
        ok=False,
        code="PII_CONSENT_REQUIRED",
        flagged_signals=("Vehicle.CurrentLocation.Latitude",),
    )
    result = _validator(governance=decision).validate(_spec())
    assert result.ok is False
    assert any(e.code == "PII_CONSENT_REQUIRED" for e in result.errors)


def test_pii_flag_must_match_when_pii_signal_present() -> None:
    decision = GovernanceDecision(
        ok=True,
        code=None,
        flagged_signals=("Vehicle.CurrentLocation.Latitude",),
    )
    # consent=True but has_pii_signal=False -> inconsistent.
    result = _validator(governance=decision).validate(_spec(pii_consent=True, has_pii_signal=False))
    assert any(e.code == "PII_FLAG_INCONSISTENT" for e in result.errors)


def test_window_out_of_bounds_check_is_defensive() -> None:
    # CollectionPolicySpec already enforces 1 <= collection_window_hours <= 168
    # at the Pydantic layer, so the validator's WINDOW_OUT_OF_BOUNDS branch is
    # a defensive check. Verify the validator handles the upper-bound case
    # by bypassing Pydantic and patching the field directly.
    spec = _spec(window=72)
    object.__setattr__(spec, "collection_window_hours", 169)
    result = _validator().validate(spec)
    assert any(e.code == "WINDOW_OUT_OF_BOUNDS" for e in result.errors)


def test_validation_result_to_retry_context_serializes_errors() -> None:
    result = ValidationResult(
        ok=False,
        errors=[ValidationError(code="X", field="f", message="m", details={"k": "v"})],
        suggestions={"a": "b"},
    )
    ctx = result.to_retry_context()
    assert ctx["validation_errors"][0]["code"] == "X"
    assert ctx["suggestions"] == {"a": "b"}
