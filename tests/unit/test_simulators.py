"""Unit tests for DiagnosticFindingGenerator + TelemetryGenerator (T134)."""

from __future__ import annotations

from datetime import datetime

import pytest

from collectmind.simulators.diagnostic_finding_generator import DiagnosticFindingGenerator
from collectmind.simulators.telemetry_generator import TelemetryGenerator


class TestDiagnosticFindingGenerator:
    def test_brake_wear_finding_shape(self) -> None:
        gen = DiagnosticFindingGenerator(seed=42)
        finding = gen.brake_wear_finding()
        assert finding["schema_version"] == "1.0.0"
        assert finding["anomaly_type"] == "brake_wear_early_stage"
        assert finding["hypothesis_class"] == "brake_wear"
        assert finding["finding_id"].startswith("F-sim-")
        assert len(finding["vehicle_scope"]) == 3
        assert 0.6 <= finding["upstream_confidence"] <= 0.9
        datetime.fromisoformat(str(finding["_simulator_emitted_at"]))

    def test_brake_wear_finding_honors_explicit_args(self) -> None:
        gen = DiagnosticFindingGenerator()
        finding = gen.brake_wear_finding(
            finding_id="F-custom",
            vehicle_count=5,
            upstream_confidence=0.55,
        )
        assert finding["finding_id"] == "F-custom"
        assert len(finding["vehicle_scope"]) == 5
        assert finding["upstream_confidence"] == pytest.approx(0.55)

    def test_seed_produces_deterministic_confidence(self) -> None:
        a = DiagnosticFindingGenerator(seed=1).brake_wear_finding(finding_id="F-a")
        b = DiagnosticFindingGenerator(seed=1).brake_wear_finding(finding_id="F-a")
        assert a["upstream_confidence"] == b["upstream_confidence"]


class _FakeConn:
    def __init__(self) -> None:
        self.executemany_calls: list[tuple[str, list]] = []

    async def executemany(self, sql: str, rows: list) -> None:
        self.executemany_calls.append((sql, rows))


class _FakeDb:
    def __init__(self) -> None:
        self.conn = _FakeConn()

    def acquire(self, tenant_id: str):  # type: ignore[no-untyped-def]
        outer = self

        class _Ctx:
            async def __aenter__(self_inner) -> _FakeConn:
                return outer.conn

            async def __aexit__(self_inner, *_a) -> None:
                return None

        return _Ctx()


class TestTelemetryGenerator:
    @pytest.mark.asyncio
    async def test_starve_directive_writes_nothing(self) -> None:
        db = _FakeDb()
        gen = TelemetryGenerator(db)  # type: ignore[arg-type]
        rows = await gen.simulate(
            tenant_id="t",
            policy={
                "vehicle_scope": ["VIN-1"],
                "signals": [{"vss_name": "Vehicle.Foo"}],
                "confidence_threshold": 0.5,
            },
            deployment_id="d-1",
            directive="starve",
        )
        assert rows == 0
        assert db.conn.executemany_calls == []

    @pytest.mark.asyncio
    async def test_empty_scope_writes_nothing(self) -> None:
        db = _FakeDb()
        gen = TelemetryGenerator(db)  # type: ignore[arg-type]
        rows = await gen.simulate(
            tenant_id="t",
            policy={"vehicle_scope": [], "signals": [{"vss_name": "x"}]},
            deployment_id="d",
            directive=None,
        )
        assert rows == 0

    @pytest.mark.asyncio
    async def test_confirm_writes_above_threshold_values(self) -> None:
        db = _FakeDb()
        gen = TelemetryGenerator(db)  # type: ignore[arg-type]
        rows = await gen.simulate(
            tenant_id="t",
            policy={
                "vehicle_scope": ["VIN-1", "VIN-2"],
                "signals": [{"vss_name": "Vehicle.A"}, {"vss_name": "Vehicle.B"}],
                "confidence_threshold": 0.4,
                "policy_id": "policy-x",
                "version": "1.0.0",
            },
            deployment_id="d-1",
            directive="confirm",
        )
        # 20 ticks * 2 vehicles * 2 signals = 80 rows
        assert rows == 80
        assert len(db.conn.executemany_calls) == 1
        _sql, batch = db.conn.executemany_calls[0]
        # Confirm directive produces values >= threshold + 0.05
        for row in batch:
            value = float(row[3])
            assert value >= 0.45 - 1e-9

    @pytest.mark.asyncio
    async def test_rule_out_writes_below_threshold_values(self) -> None:
        db = _FakeDb()
        gen = TelemetryGenerator(db)  # type: ignore[arg-type]
        rows = await gen.simulate(
            tenant_id="t",
            policy={
                "vehicle_scope": ["VIN-1"],
                "signals": [{"vss_name": "Vehicle.A"}],
                "confidence_threshold": 0.8,
            },
            deployment_id="d",
            directive="rule_out",
        )
        assert rows == 20
        _sql, batch = db.conn.executemany_calls[0]
        for row in batch:
            value = float(row[3])
            assert value <= 0.8 - 0.2 + 1e-9
