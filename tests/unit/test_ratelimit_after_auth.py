"""T253: rate-limit decisions happen AFTER JWT verification.

Asserts FR-017: a request that fails JWT verification MUST NOT increment any tenant's
rate-limit counter — the limiter is gated behind the auth dependency in the FastAPI
dependency chain so an unauthenticated request never reaches the bucket.

Watch-point 3 (user's note): on auth-failure, NEITHER
``collectmind_ratelimit_throttled_total`` NOR
``collectmind_ratelimit_redis_unavailable_total`` should fire. The request fails before
the limiter is called at all.

Red phase: Phase 10.b T255 + T259 wire the middleware into the FastAPI dependency chain;
T258 registers the metrics. Until then, the metrics don't exist (Counter has 0 series) and
the test passes vacuously. To convert vacuous-green to honest-red on the "metrics exist"
side, the test asserts that the metrics ARE registered (which fails before T258 lands).

Anchors: FR-017 / Principle IX / Principle IV.
"""

from __future__ import annotations

import httpx

from tests.conftest import (
    ORCHESTRATION_BASE_URL,
    require_local_stack,
)


def _metric_value(metric_name: str) -> int:
    response = httpx.get(f"{ORCHESTRATION_BASE_URL}/metrics", timeout=5.0)
    if response.status_code != 200:
        return 0
    total = 0
    for line in response.text.splitlines():
        if line.startswith("#") or not line.startswith(metric_name):
            continue
        try:
            value = float(line.rsplit(" ", 1)[-1])
        except (ValueError, IndexError):
            continue
        total += int(value)
    return total


def _metric_registered(metric_name: str) -> bool:
    """Return True iff the named metric appears in /metrics (either as a series or as a
    `# HELP` line for an as-yet-uninvoked counter)."""
    response = httpx.get(f"{ORCHESTRATION_BASE_URL}/metrics", timeout=5.0)
    if response.status_code != 200:
        return False
    return metric_name in response.text


def test_throttled_metric_is_registered() -> None:
    """Phase 10.b T258 must register ``collectmind_ratelimit_throttled_total`` even when
    no requests have hit the limit yet. Red signal: metric absent from /metrics scrape."""
    require_local_stack()
    assert _metric_registered(
        "collectmind_ratelimit_throttled_total"
    ), "Phase 10.b T258 has not landed: collectmind_ratelimit_throttled_total not in /metrics"


def test_redis_unavailable_metric_is_registered() -> None:
    """Phase 10.b T258 must register ``collectmind_ratelimit_redis_unavailable_total``."""
    require_local_stack()
    assert _metric_registered(
        "collectmind_ratelimit_redis_unavailable_total"
    ), "Phase 10.b T258 has not landed: collectmind_ratelimit_redis_unavailable_total not in /metrics"


def test_auth_failure_does_not_advance_ratelimit_counter() -> None:
    """FR-017: bogus JWT → 401, no counter increment for any tenant."""
    require_local_stack()
    before_throttled = _metric_value("collectmind_ratelimit_throttled_total")
    before_unavailable = _metric_value("collectmind_ratelimit_redis_unavailable_total")

    # 100 bogus-token requests in tight loop.
    headers = {"Authorization": "Bearer not-a-real-jwt", "Content-Type": "application/json"}
    body = {
        "tenant_id": "tenant-a",
        "finding_id": "f-auth-fail",
        "schema_version": "1.0.0",
        "anomaly_type": "test",
        "hypothesis_class": "brake-wear-early-stage",
        "hypothesis_statement": "test",
        "candidate_signals": [],
        "vehicle_scope": [],
        "upstream_confidence": 0.5,
    }
    for _ in range(100):
        response = httpx.post(
            f"{ORCHESTRATION_BASE_URL}/api/v1/findings",
            headers=headers,
            json=body,
            timeout=5.0,
        )
        assert response.status_code == 401, f"unauthenticated request should 401; got {response.status_code}"

    after_throttled = _metric_value("collectmind_ratelimit_throttled_total")
    after_unavailable = _metric_value("collectmind_ratelimit_redis_unavailable_total")
    assert after_throttled == before_throttled, (
        f"FR-017 violation: throttled_total advanced on auth-failure "
        f"({before_throttled} → {after_throttled}). The rate-limit middleware MUST run AFTER "
        f"the auth dependency; an unauthenticated request must never reach the limiter."
    )
    assert after_unavailable == before_unavailable, (
        f"FR-017 + watch-point 3 violation: redis_unavailable_total advanced on auth-failure "
        f"({before_unavailable} → {after_unavailable})."
    )
