"""T285 coverage sweep: LogicalTimeScheduler unit tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from collectmind.feedback.scheduler import LogicalTimeScheduler


def test_default_factor_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIME_ACCELERATION_FACTOR", "10")
    assert LogicalTimeScheduler().factor == 10.0


def test_explicit_factor_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIME_ACCELERATION_FACTOR", "10")
    assert LogicalTimeScheduler(factor=5.0).factor == 5.0


def test_factor_zero_raises() -> None:
    with pytest.raises(ValueError, match="must be > 0"):
        LogicalTimeScheduler(factor=0.0)


def test_factor_negative_raises() -> None:
    with pytest.raises(ValueError, match="must be > 0"):
        LogicalTimeScheduler(factor=-1.0)


def test_expires_at_scales_by_factor() -> None:
    """A 24-hour window under factor=10000 expires in 8.64 seconds wall-clock."""
    opened = datetime(2026, 5, 11, 0, 0, 0, tzinfo=UTC)
    scheduler = LogicalTimeScheduler(factor=10000.0)
    expires = scheduler.expires_at(opened, window_hours=24)
    delta = (expires - opened).total_seconds()
    assert abs(delta - 8.64) < 0.001


def test_now_returns_aware_datetime() -> None:
    assert LogicalTimeScheduler().now().tzinfo is UTC


def test_default_factor_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TIME_ACCELERATION_FACTOR", raising=False)
    assert LogicalTimeScheduler().factor == 1.0


def test_invalid_env_value_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty / zero env value falls back to default 1.0 per the ``or 1.0`` guard."""
    monkeypatch.setenv("TIME_ACCELERATION_FACTOR", "0")
    assert LogicalTimeScheduler().factor == 1.0
