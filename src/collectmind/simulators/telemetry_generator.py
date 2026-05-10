"""Synthetic post-collection telemetry (T102).

Writes observations into telemetry_observations parameterized by deployed policy.
The directive header on POST /findings (X-Telemetry-Simulator-Directive) controls
whether the synthetic stream confirms, rules out, or starves the hypothesis.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from typing import Any

import structlog

from collectmind.registry.db import Database


logger = structlog.get_logger(__name__)


class TelemetryGenerator:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._random = random.Random(0xBEAD)

    async def simulate(
        self,
        *,
        tenant_id: str,
        policy: dict[str, Any],
        deployment_id: str,
        directive: str | None,
    ) -> int:
        scope = list(policy.get("vehicle_scope", []))
        signals = [s["vss_name"] for s in policy.get("signals", [])]
        if not scope or not signals or directive == "starve":
            return 0
        threshold = float(policy.get("confidence_threshold", 0.5))
        # Choose a value distribution aligned with the directive.
        if directive == "rule_out":
            generator = lambda: max(0.0, threshold - self._random.uniform(0.2, 0.5))  # noqa: E731
        else:
            # Default and "confirm" directives both produce above-threshold values.
            generator = lambda: min(1.0, threshold + self._random.uniform(0.05, 0.3))  # noqa: E731

        rows: list[tuple[str, str, str, float, datetime, dict[str, Any], str]] = []
        now = datetime.now(tz=timezone.utc)
        for i in range(20):
            ts = now + timedelta(seconds=i)
            for vehicle in scope:
                for signal in signals:
                    rows.append(
                        (
                            tenant_id,
                            vehicle,
                            signal,
                            generator(),
                            ts,
                            {
                                "tenant_id": tenant_id,
                                "policy_id": policy.get("policy_id", ""),
                                "version": policy.get("version", "1.0.0"),
                            },
                            "simulator",
                        )
                    )
        async with self._db.acquire(tenant_id) as conn:
            await conn.executemany(
                """
                INSERT INTO telemetry_observations (
                  tenant_id, vehicle_id, signal_name, value, observed_at, policy_ref, source
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                """,
                [
                    (
                        r[0],
                        r[1],
                        r[2],
                        float(r[3]),
                        r[4],
                        __import__("json").dumps(r[5]),
                        r[6],
                    )
                    for r in rows
                ],
            )
        logger.info(
            "telemetry_simulated",
            tenant_id=tenant_id,
            deployment_id=deployment_id,
            rows=len(rows),
            directive=directive or "default",
        )
        return len(rows)
