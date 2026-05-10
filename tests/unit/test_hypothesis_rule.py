"""T056: Brake-wear hypothesis evaluation rule.

Outcome enum: confirmed / ruled_out / no_data. The rule is invoked by the feedback
worker (T093) when a collection window closes.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


def _obs(value: float, signal: str = "Vehicle.Chassis.Brake.PadWear", dt_minutes: int = 0):
    """Helper to construct a TelemetryObservation-like dict."""
    return {
        "vehicle_id": "VIN-1",
        "signal_name": signal,
        "value": value,
        "observed_at": datetime(2026, 5, 9, 14, dt_minutes, tzinfo=timezone.utc),
        "source": "simulator",
    }


def test_no_observations_returns_no_data() -> None:
    from collectmind.feedback.evaluator import BrakeWearHypothesisRule

    rule = BrakeWearHypothesisRule()
    outcome = rule.evaluate(observations=[], expected_threshold=0.7)
    assert outcome.hypothesis_state == "no_data"
    assert outcome.signals_collected_count == 0


def test_observations_above_threshold_confirm() -> None:
    from collectmind.feedback.evaluator import BrakeWearHypothesisRule

    rule = BrakeWearHypothesisRule()
    obs = [_obs(0.8 + i * 0.01, dt_minutes=i) for i in range(10)]
    outcome = rule.evaluate(observations=obs, expected_threshold=0.7)
    assert outcome.hypothesis_state == "confirmed"
    assert outcome.signals_collected_count == 10
    assert outcome.data_quality_score > 0.5


def test_observations_below_threshold_ruled_out() -> None:
    from collectmind.feedback.evaluator import BrakeWearHypothesisRule

    rule = BrakeWearHypothesisRule()
    obs = [_obs(0.1 + i * 0.01, dt_minutes=i) for i in range(10)]
    outcome = rule.evaluate(observations=obs, expected_threshold=0.7)
    assert outcome.hypothesis_state == "ruled_out"
    assert outcome.signals_collected_count == 10


def test_mixed_observations_ruled_out_when_majority_below() -> None:
    from collectmind.feedback.evaluator import BrakeWearHypothesisRule

    rule = BrakeWearHypothesisRule()
    obs = [_obs(0.8, dt_minutes=0), _obs(0.2, dt_minutes=1), _obs(0.3, dt_minutes=2)]
    outcome = rule.evaluate(observations=obs, expected_threshold=0.7)
    assert outcome.hypothesis_state == "ruled_out"


@pytest.mark.parametrize("threshold", [0.0, 0.5, 1.0])
def test_threshold_is_inclusive_on_confirm(threshold: float) -> None:
    """At value == threshold, the rule confirms the hypothesis (inclusive-on-confirm)."""
    from collectmind.feedback.evaluator import BrakeWearHypothesisRule

    rule = BrakeWearHypothesisRule()
    obs = [_obs(threshold, dt_minutes=0)]
    outcome = rule.evaluate(observations=obs, expected_threshold=threshold)
    assert outcome.hypothesis_state == "confirmed"
