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


# ─── T250: feature-002 multi-tenant noisy-neighbor profile ────────────────────
# Asserts SC-003 (≥80% of A's over-budget requests are rejected) + SC-004 (B's p95 is
# unaffected by A's burst — within 10% of the feature-001 SC-001 baseline).
#
# Invocation (sets MULTI_TENANT_MODE=1 to enable the MultiTenantUser class):
#   MULTI_TENANT_MODE=1 locust -f tests/load/locustfile_smoke.py \
#     --headless --users 100 --spawn-rate 50 --run-time 60s \
#     --host $ORCHESTRATION_BASE_URL --csv reports/multitenant
#
# Tenant-A bursts at 5× its FR-012 default (10000 r/s inbound); tenant-B sustains at
# 0.5× its default (1000 r/s). Wait-times tuned so A drives the rate-limit limiter
# while B stays comfortably under.
#
# Phase 10.a red-phase: SC-003 + SC-004 hooks fail because the rate-limit middleware
# isn't wired (Phase 10.b T255). The smoke profile is the load-tier confirmation that
# the Phase 10.b implementation actually throttles A without affecting B.

MULTI_TENANT_MODE = os.environ.get("MULTI_TENANT_MODE", "0") == "1"
TENANT_A_REJECT_RATIO_FLOOR = float(os.environ.get("TENANT_A_REJECT_RATIO_FLOOR", "0.80"))
TENANT_B_P95_CEILING_MS = int(os.environ.get("TENANT_B_P95_CEILING_MS", "12000"))


if MULTI_TENANT_MODE:

    class TenantANoisyUser(HttpUser):
        """Bursts tenant-A at 5× its configured rate limit. Expects ≥80% rejections."""

        wait_time = between(0.001, 0.002)  # tight loop → ~500-1000 r/s per worker
        weight = 5

        def on_start(self) -> None:
            self._token = mint_token(tenant="tenant-a")

        @task
        def burst(self) -> None:
            self.client.post(
                "/api/v1/findings",
                json=finding_payload(tenant="tenant-a"),
                headers={"Authorization": f"Bearer {self._token}"},
                name="POST /api/v1/findings (tenant-a burst)",
            )

    class TenantBQuietUser(HttpUser):
        """Tenant-B sustains at 0.5× its rate limit. Expects p95 unaffected by A's burst."""

        wait_time = between(1.5, 2.5)
        weight = 1

        def on_start(self) -> None:
            self._token = mint_token(tenant="tenant-b")

        @task
        def steady(self) -> None:
            self.client.post(
                "/api/v1/findings",
                json=finding_payload(tenant="tenant-b"),
                headers={"Authorization": f"Bearer {self._token}"},
                name="POST /api/v1/findings (tenant-b steady)",
            )

    @events.quitting.add_listener
    def _enforce_multitenant_slos(environment, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        a_stats = environment.stats.get("POST /api/v1/findings (tenant-a burst)", "POST")
        b_stats = environment.stats.get("POST /api/v1/findings (tenant-b steady)", "POST")
        if a_stats is None or b_stats is None:
            logger.error("multitenant profile: missing per-tenant stats; cannot enforce SC-003/SC-004")
            environment.process_exit_code = 1
            return

        a_total = a_stats.num_requests
        a_429 = a_stats.num_failures  # locust counts non-2xx as failures
        a_reject_ratio = (a_429 / a_total) if a_total > 0 else 0.0

        b_p95_ms = b_stats.get_response_time_percentile(0.95) or 0

        if a_reject_ratio < TENANT_A_REJECT_RATIO_FLOOR:
            logger.error(
                "SC-003 violation: tenant-A rejection ratio %.3f below floor %.3f "
                "(429s out of %d requests = %d)",
                a_reject_ratio, TENANT_A_REJECT_RATIO_FLOOR, a_total, a_429,
            )
            environment.process_exit_code = 1
        if b_p95_ms > TENANT_B_P95_CEILING_MS:
            logger.error(
                "SC-004 violation: tenant-B p95 %.0fms exceeds ceiling %dms during A's burst",
                b_p95_ms, TENANT_B_P95_CEILING_MS,
            )
            environment.process_exit_code = 1
