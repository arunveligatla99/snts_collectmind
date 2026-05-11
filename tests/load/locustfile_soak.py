"""T118 — 24-hour soak on the self-hosted GPU runner (nightly).

Asserts SC-003: at 50 percent of SC-002's peak rate, the system runs for at
least 24 hours with no resident-memory growth above 5 percent and an error
rate at most 0.1 percent. Per Constitution Principle XIV this profile runs
only on the nightly schedule (``.github/workflows/nightly.yaml``, T121) and
not on every PR.

The error-rate assertion is enforced here in the locust ``quitting`` hook.
The memory-growth assertion is enforced separately by the nightly workflow:
the workflow snapshots ``process_resident_memory_bytes{job="orchestration-api"}``
at run start, again at run end, asserts (end - start) / start <= 0.05, and
fails the build otherwise. Keeping the memory check in the workflow rather
than in the locust process makes the soak portable across runtimes and lets
the workflow attach the time-series snapshot as a CI artifact regardless of
whether the locust process exited cleanly.

Invoked by the nightly workflow:

    locust -f tests/load/locustfile_soak.py \\
      --headless --users 500 --spawn-rate 25 --run-time 24h \\
      --host $ORCHESTRATION_BASE_URL --csv reports/soak

Assertions (enforced via ``quitting`` hook):

- Failure ratio at most 0.001 (SC-003's 0.1% error-rate ceiling).
- p95 response time at most 12 seconds (SC-001 p95 ceiling holds at 50% load).

Memory-growth assertion lives in the nightly workflow as documented above.
"""

from __future__ import annotations

import logging
import os

from locust import HttpUser, constant_pacing, events, task

from tests.load._common import finding_payload, mint_token

logger = logging.getLogger(__name__)

SOAK_FAILURE_RATIO_CEILING = float(os.environ.get("SOAK_FAILURE_RATIO_CEILING", "0.001"))  # SC-003
SOAK_P95_CEILING_MS = int(os.environ.get("SOAK_P95_CEILING_MS", "12000"))  # SC-001 p95 holds at 50% load


class CollectMindSoakUser(HttpUser):
    # 500 users x 1 req/s = 500 events/s/tenant, which is 50% of SC-002's
    # 1000 events/s/tenant peak per SC-003's "50 percent of peak."
    wait_time = constant_pacing(1.0)

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
def _enforce_soak_slos(environment, **_kwargs) -> None:  # type: ignore[no-untyped-def]
    stats = environment.stats
    total = stats.total
    failure_ratio = total.fail_ratio
    p95_ms = total.get_response_time_percentile(0.95)

    if failure_ratio > SOAK_FAILURE_RATIO_CEILING:
        logger.error(
            "soak failure ratio %.6f exceeds SC-003 ceiling %.6f",
            failure_ratio,
            SOAK_FAILURE_RATIO_CEILING,
        )
        environment.process_exit_code = 1
    if p95_ms is not None and p95_ms > SOAK_P95_CEILING_MS:
        logger.error(
            "soak p95 %.0fms exceeds SC-001 ceiling %dms",
            p95_ms,
            SOAK_P95_CEILING_MS,
        )
        environment.process_exit_code = 1
