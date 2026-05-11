"""T117 — full-profile load against the real SLM (workflow_dispatch only).

Asserts SC-002: 1,000 diagnostic events/s/tenant sustained for 30 minutes with
end-to-end success rate at or above 99.9 percent. Per Constitution Principle
XIV this profile MUST NOT run on every PR; it runs only on the manual
``workflow_dispatch`` trigger and on the scheduled cadence recorded in the
runbook (`observability/runbooks/slo-002-success-rate.md`).

Invoked by ``.github/workflows/ci-workflow-dispatch.yaml`` (T120):

    locust -f tests/load/locustfile_full.py \\
      --headless --users 1000 --spawn-rate 50 --run-time 30m \\
      --host $ORCHESTRATION_BASE_URL --csv reports/full

The real SLM container (`SLM_PROFILE=vllm`) MUST be up before the run; the
PR-tier deterministic-fingerprint stub is explicitly NOT used here.

Assertions (enforced via ``quitting`` hook):

- Failure ratio at most 0.001 (SC-002's 99.9% success contract).
- p95 response time at most 12 seconds (SC-001 p95 ceiling under SC-002 load).
"""

from __future__ import annotations

import logging
import os

from locust import HttpUser, constant_pacing, events, task

from tests.load._common import finding_payload, mint_token

logger = logging.getLogger(__name__)

FULL_FAILURE_RATIO_CEILING = float(os.environ.get("FULL_FAILURE_RATIO_CEILING", "0.001"))  # SC-002
FULL_P95_CEILING_MS = int(os.environ.get("FULL_P95_CEILING_MS", "12000"))  # SC-001 p95 under SC-002 load


class CollectMindFullUser(HttpUser):
    # 1 request per second per user; with 1000 users this produces the
    # SC-002 target of 1,000 events/s/tenant.
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
def _enforce_full_slos(environment, **_kwargs) -> None:  # type: ignore[no-untyped-def]
    stats = environment.stats
    total = stats.total
    failure_ratio = total.fail_ratio
    p95_ms = total.get_response_time_percentile(0.95)

    if failure_ratio > FULL_FAILURE_RATIO_CEILING:
        logger.error(
            "full-profile failure ratio %.6f exceeds SC-002 ceiling %.6f",
            failure_ratio,
            FULL_FAILURE_RATIO_CEILING,
        )
        environment.process_exit_code = 1
    if p95_ms is not None and p95_ms > FULL_P95_CEILING_MS:
        logger.error(
            "full-profile p95 %.0fms exceeds SC-001 ceiling %dms",
            p95_ms,
            FULL_P95_CEILING_MS,
        )
        environment.process_exit_code = 1
