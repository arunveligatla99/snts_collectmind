"""BrakeWearHypothesisRule (T092). Confirmed / ruled_out / no_data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HypothesisOutcome:
    hypothesis_state: str
    signals_collected_count: int
    data_quality_score: float
    evidence_summary: dict[str, Any]


class BrakeWearHypothesisRule:
    """Rule: majority of observations at-or-above threshold confirms; below rules out."""

    def evaluate(
        self,
        observations: list[dict[str, Any]],
        expected_threshold: float,
    ) -> HypothesisOutcome:
        count = len(observations)
        if count == 0:
            return HypothesisOutcome(
                hypothesis_state="no_data",
                signals_collected_count=0,
                data_quality_score=0.0,
                evidence_summary={},
            )

        above = 0
        below = 0
        for obs in observations:
            value = float(obs.get("value", 0.0))
            if value >= expected_threshold:
                above += 1
            else:
                below += 1

        confirmed = above >= below and above > 0
        state = "confirmed" if confirmed else "ruled_out"
        # Quality score scales with sample volume up to a cap; below 5 samples it is
        # weighted down, so a single observation does not score 1.0.
        quality = min(1.0, count / 10.0)
        return HypothesisOutcome(
            hypothesis_state=state,
            signals_collected_count=count,
            data_quality_score=round(quality, 3),
            evidence_summary={"above_threshold": above, "below_threshold": below},
        )
