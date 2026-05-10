"""Synthetic upstream diagnostic findings (T101)."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone


class DiagnosticFindingGenerator:
    def __init__(self, seed: int = 0xCAFE) -> None:
        self._random = random.Random(seed)

    def brake_wear_finding(
        self,
        finding_id: str | None = None,
        vehicle_count: int = 3,
        upstream_confidence: float | None = None,
    ) -> dict[str, object]:
        confidence = upstream_confidence if upstream_confidence is not None else self._random.uniform(0.6, 0.9)
        return {
            "schema_version": "1.0.0",
            "finding_id": finding_id or f"F-sim-{uuid.uuid4().hex[:8]}",
            "anomaly_type": "brake_wear_early_stage",
            "hypothesis_class": "brake_wear",
            "hypothesis_statement": "rotor temperature excursions correlated with mileage",
            "candidate_signals": [
                "Vehicle.Chassis.Brake.PadWear",
                "Vehicle.Powertrain.CombustionEngine.EngineOilTemperature",
            ],
            "vehicle_scope": [f"VIN-sim-{i:03d}" for i in range(vehicle_count)],
            "upstream_confidence": round(confidence, 3),
            "_simulator_emitted_at": datetime.now(tz=timezone.utc).isoformat(),
        }
