"""T116 — PR-tier smoke load (deterministic fingerprint stub, ~60s).

Asserts that the full downstream path holds under modest concurrency without
invoking the SLM. Per Constitution Principle XIV smoke load uses the
deterministic-fingerprint stub (ADR-0004), never the real model. The PR-tier
CI workflow invokes:

    locust -f tests/load/locustfile_smoke.py \\
      --headless --users 50 --spawn-rate 10 --run-time 60s \\
      --host $ORCHESTRATION_BASE_URL --csv reports/smoke

The smoke profile is the SC-009 budget gate's load contribution. The user
count and run-time are sized so a healthy PR-tier stack completes in under
two minutes wall-clock.

Assertions (enforced via the ``quitting`` hook):

- Failure ratio is zero (no 5xx, no validation errors, no timeouts).
- Median (p50) response time is at most 4 seconds (the SC-001 p50 ceiling).

A failed assertion exits the locust process with a non-zero return code so
the CI step fails the build.
"""

from __future__ import annotations

import logging
import os

from locust import HttpUser, between, events, task

from tests.load._common import finding_payload, mint_token

logger = logging.getLogger(__name__)

SMOKE_P50_CEILING_MS = int(os.environ.get("SMOKE_P50_CEILING_MS", "4000"))  # SC-001 p50
SMOKE_FAILURE_RATIO_CEILING = float(os.environ.get("SMOKE_FAILURE_RATIO_CEILING", "0.0"))


class CollectMindSmokeUser(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self) -> None:
        self._token = mint_token()

    @task
    def publish_finding(self) -> None:
        self.client.post(
            "/api/v1/findings",
            json=finding_payload(),
            headers={"Authorization": f"Bearer {self._token}"},
            name="POST /api/v1/findings",
        )


@events.quitting.add_listener
def _enforce_smoke_slos(environment, **_kwargs) -> None:  # type: ignore[no-untyped-def]
    stats = environment.stats
    total = stats.total
    failure_ratio = total.fail_ratio
    p50_ms = total.get_response_time_percentile(0.50)

    if failure_ratio > SMOKE_FAILURE_RATIO_CEILING:
        logger.error(
            "smoke failure ratio %.6f exceeds ceiling %.6f",
            failure_ratio,
            SMOKE_FAILURE_RATIO_CEILING,
        )
        environment.process_exit_code = 1
    if p50_ms is not None and p50_ms > SMOKE_P50_CEILING_MS:
        logger.error(
            "smoke p50 %.0fms exceeds ceiling %dms (SC-001)",
            p50_ms,
            SMOKE_P50_CEILING_MS,
        )
        environment.process_exit_code = 1
