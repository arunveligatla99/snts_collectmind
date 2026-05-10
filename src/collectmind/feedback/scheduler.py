"""LogicalTimeScheduler (T091). Time-acceleration factor per FR-009a."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone


class LogicalTimeScheduler:
    """Maps logical-window durations to wall-clock via TIME_ACCELERATION_FACTOR."""

    def __init__(self, factor: float | None = None) -> None:
        if factor is None:
            factor = float(os.environ.get("TIME_ACCELERATION_FACTOR", "1.0") or 1.0) or 1.0
        if factor <= 0:
            raise ValueError(f"TIME_ACCELERATION_FACTOR must be > 0; got {factor!r}")
        self._factor = factor

    @property
    def factor(self) -> float:
        return self._factor

    def expires_at(self, opened_at: datetime, window_hours: int) -> datetime:
        seconds = (window_hours * 3600) / self._factor
        return opened_at + timedelta(seconds=seconds)

    def now(self) -> datetime:
        return datetime.now(tz=timezone.utc)
