"""Rate-limit Prometheus metrics (feature 002 / T258 / ADR-0008 Part 6).

Three counters with DISTINCT semantics (per the user's Phase 10.b watch-point 3):

    collectmind_ratelimit_decision_total{tenant_id, endpoint, decision}
        Per-decision counter. ``decision`` in {"allow", "reject"}. The full denominator
        of every rate-limit decision the middleware made.

    collectmind_ratelimit_throttled_total{tenant_id, endpoint}
        Counter that increments ONLY when a request is rejected by the limiter.
        Drives the ``RatelimitSustainedThrottle`` page-tier alert (Phase 13 T280).

    collectmind_ratelimit_redis_unavailable_total{endpoint}
        Counter that increments ONLY when the Redis Lua call fails (connection refused,
        timeout, MOVED/ASK redirect, NOSCRIPT). Drives the ``RatelimitRedisUnavailable``
        page-tier alert (Phase 13 T280). MUST NOT fire on rate-limit-rejection scenarios.

The DISTINCT-counter design means the two alerts route to two different runbook pages
and the operator can disambiguate "the limiter is doing its job" from "the limiter is
broken" at a glance.
"""

from __future__ import annotations

from prometheus_client import Counter

ratelimit_decision_total: Counter = Counter(
    "collectmind_ratelimit_decision_total",
    "Per-tenant rate-limit decisions (allow/reject) per endpoint.",
    labelnames=("tenant_id", "endpoint", "decision"),
)

ratelimit_throttled_total: Counter = Counter(
    "collectmind_ratelimit_throttled_total",
    "Rate-limit rejections per tenant per endpoint. Fires only on a 429 decision.",
    labelnames=("tenant_id", "endpoint"),
)

ratelimit_redis_unavailable_total: Counter = Counter(
    "collectmind_ratelimit_redis_unavailable_total",
    "Redis-unavailable failures in the rate-limit middleware. Fires only on a 503 "
    "(failure-closed) decision; MUST NOT fire when the rate limit is hit.",
    labelnames=("endpoint",),
)
