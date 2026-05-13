"""T249: failure-closed posture under Redis outage.

Asserts ADR-0008 Part 3 contract: when the Redis Lua script fails (connection refused,
timeout > 1 s, MOVED/ASK redirection during failover, script eviction), the middleware
responds with ``503 Service Unavailable`` carrying ``Retry-After: 1``. The middleware MUST
NOT silently allow the request.

Watch-points (user's notes):
    2. **DISTINCT status codes**: 503 here (Redis unreachable) vs 429 in T247 (rate-limit
       hit). Two conditions, two response shapes.
    3. **DISTINCT metric**: ``collectmind_ratelimit_redis_unavailable_total{endpoint}``
       fires HERE; ``collectmind_ratelimit_throttled_total`` does NOT.

Red phase: Phase 10.b T255 (middleware.py) hasn't landed. Stopping Redis has no effect on
the inbound request path (no limiter is wired). Test fails because the response is 202 or
500, not 503.

Anchors: ADR-0008 Part 3 / Principle IV / Principle IX (failure-closed = security primitive).
"""

from __future__ import annotations

import subprocess
import time

import httpx
import pytest

from tests.conftest import (
    ORCHESTRATION_BASE_URL,
    TENANT_A,
    mint_tenant_token,
    require_local_stack,
)

pytestmark = pytest.mark.integration

REDIS_CONTAINER = "collectmind-redis"
THROTTLED_METRIC = "collectmind_ratelimit_throttled_total"
REDIS_UNAVAILABLE_METRIC = "collectmind_ratelimit_redis_unavailable_total"


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


def _stop_redis() -> None:
    subprocess.run(["docker", "stop", REDIS_CONTAINER], capture_output=True, timeout=15)


def _start_redis() -> None:
    subprocess.run(["docker", "start", REDIS_CONTAINER], capture_output=True, timeout=15)
    # Wait for Redis to be back.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", REDIS_CONTAINER, "redis-cli", "PING"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "PONG" in result.stdout:
            return
        time.sleep(1)
    raise RuntimeError("redis container did not come back up within 30s")


def test_redis_unavailable_returns_503_with_retry_after() -> None:
    """Stop Redis; request must return 503 + Retry-After: 1; the throttled counter must NOT fire."""
    require_local_stack()
    before_unavailable = _metric_value(REDIS_UNAVAILABLE_METRIC)
    before_throttled = _metric_value(THROTTLED_METRIC)

    token = mint_tenant_token(TENANT_A)
    _stop_redis()
    try:
        # Give the orchestration-api a moment to surface the connection failure.
        time.sleep(2)
        response = httpx.post(
            f"{ORCHESTRATION_BASE_URL}/api/v1/findings",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "tenant_id": TENANT_A,
                "finding_id": "f-redis-down",
                "schema_version": "1.0.0",
                "anomaly_type": "test",
                "hypothesis_class": "brake-wear-early-stage",
                "hypothesis_statement": "test",
                "candidate_signals": [],
                "vehicle_scope": [],
                "upstream_confidence": 0.5,
            },
            timeout=10.0,
        )
    finally:
        _start_redis()

    assert response.status_code == 503, (
        f"ADR-0008 Part 3 violation: Redis unreachable returned {response.status_code}; "
        f"expected 503 (failure-closed). A 202 here means the middleware silently allowed "
        f"the request (Phase 10.b T255 + T258 pending). A 500 means an unhandled error path "
        f"(middleware doesn't catch Redis-unavailable explicitly)."
    )
    assert response.headers.get("Retry-After") == "1", (
        f"ADR-0008 Part 3 violation: 503 response missing Retry-After: 1; "
        f"got Retry-After={response.headers.get('Retry-After')!r}"
    )

    after_unavailable = _metric_value(REDIS_UNAVAILABLE_METRIC)
    after_throttled = _metric_value(THROTTLED_METRIC)
    assert after_unavailable > before_unavailable, (
        f"watch-point 3 violation: {REDIS_UNAVAILABLE_METRIC} did not increment "
        f"({before_unavailable} → {after_unavailable}); expected to fire on Redis outage."
    )
    assert after_throttled == before_throttled, (
        f"watch-point 3 violation: {THROTTLED_METRIC} incremented during a Redis-unreachable "
        f"scenario ({before_throttled} → {after_throttled}). This counter MUST fire ONLY when "
        f"the rate limit is hit (T247), not when Redis is down."
    )
