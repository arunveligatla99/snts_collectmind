"""T053: VSS validator unit tests with hypothesis property-based coverage.

Covers: valid signal name accepted; invalid name rejected with closest-suggestion;
PII-adjacent signal flagged; consent-flag enforcement.

Until T071 (`src/collectmind/validator/vss.py`) and T072 (`governance.py`) land, the
imports fail. That is the test's red phase per Principle IV.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st


@pytest.fixture(scope="module")
def validator():
    from collectmind.validator.vss import VSSValidator

    return VSSValidator.from_default_config()


@pytest.fixture(scope="module")
def governance():
    from collectmind.validator.governance import DataGovernanceChecker

    return DataGovernanceChecker.from_default_config()


def test_known_signal_accepted(validator) -> None:
    assert validator.is_valid("Vehicle.Speed")
    result = validator.validate_signal("Vehicle.Speed")
    assert result.ok is True
    assert result.suggestion is None


def test_unknown_signal_rejected_with_suggestion(validator) -> None:
    result = validator.validate_signal("Vehicle.Spee")  # one-edit-distance miss
    assert result.ok is False
    assert result.code == "VSS_INVALID_SIGNAL"
    assert result.suggestion == "Vehicle.Speed"


def test_unknown_signal_no_suggestion_far(validator) -> None:
    result = validator.validate_signal("ThisIsNotAVssSignalAtAllFoo")
    assert result.ok is False
    assert result.code == "VSS_INVALID_SIGNAL"
    assert result.suggestion is None


def test_pii_signal_requires_consent(governance) -> None:
    decision = governance.evaluate_signals(
        ["Vehicle.CurrentLocation.Latitude"], consent=False
    )
    assert decision.ok is False
    assert decision.code == "PII_CONSENT_REQUIRED"
    # flagged_signals contains the literal selected leaf names that match a PII branch.
    assert any(s.startswith("Vehicle.CurrentLocation") for s in decision.flagged_signals)


def test_pii_signal_with_consent_passes(governance) -> None:
    decision = governance.evaluate_signals(
        ["Vehicle.CurrentLocation.Latitude"], consent=True
    )
    assert decision.ok is True


def test_non_pii_signal_passes_without_consent(governance) -> None:
    decision = governance.evaluate_signals(["Vehicle.Speed"], consent=False)
    assert decision.ok is True


@given(name=st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=64))
@settings(max_examples=200, deadline=None)
def test_validator_never_raises_on_arbitrary_string(validator, name: str) -> None:
    """The validator must classify any string as ok-or-not without raising."""
    result = validator.validate_signal(name)
    assert isinstance(result.ok, bool)


@given(
    signals=st.lists(
        st.sampled_from(
            [
                "Vehicle.Speed",
                "Vehicle.CurrentLocation.Latitude",
                "Vehicle.Cabin.Driver.HeartRate",
                "Vehicle.OBD.Speed",
            ]
        ),
        min_size=1,
        max_size=5,
        unique=True,
    ),
    consent=st.booleans(),
)
@settings(max_examples=100, deadline=None)
def test_governance_pii_outcome_consistent_with_consent(governance, signals, consent) -> None:
    decision = governance.evaluate_signals(signals, consent=consent)
    pii_present = any(s.startswith(("Vehicle.CurrentLocation", "Vehicle.Cabin.Driver")) for s in signals)
    if pii_present and not consent:
        assert decision.ok is False
    else:
        assert decision.ok is True
