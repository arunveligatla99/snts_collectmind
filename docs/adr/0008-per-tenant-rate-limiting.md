# ADR-0008: Per-tenant ingress rate limiting + hot-store key migration

- Status: Proposed
- Date: 2026-05-11
- Deciders: Arun Veligatla (project author)
- Constitutional principle: IX (Security as a First-Class Requirement); XI (Performance SLOs Are Measured, Not Aspired); XVII (Audit Is a Feature, Not a Log)

## Context

Feature 002 introduces two operational primitives that protect shared infrastructure when one tenant misbehaves: per-tenant ingress rate limiting (Spec US2) and tenant-scoped hot-store keys (Spec US3). Both touch the request hot path of the orchestration-api at SC-002's sustained-ingest rate (1000 events/s/tenant); both must be implemented with bounded latency overhead so feature-001 SC-001/SC-006 budgets are preserved within 10% (Spec SC-005, SC-006).

The clarify session of 2026-05-11 resolved the user-facing surface decisions: per-tenant rate limits default to 2000 r/s + burst 4000 (inbound) and 200 r/s + burst 400 (query), persisted in Postgres `tenant_config` with RLS-protected tenant-self-reads and service-principal-only writes (Spec FR-012, FR-013). The rate-limit-versus-SLO distinction is binding (Spec FR-012a). This ADR records the engineering decisions that follow: the token-bucket algorithm, the counter storage, the cache-reload mechanism, the failure-mode posture, and the hot-store key migration mechanism (research §2).

## Decision

### Part 1 — Rate-limit defaults and the rate-limit-vs-SLO distinction

The defaults from Spec FR-012:

- Inbound endpoint (`POST /api/v1/findings`): 2000 requests per second sustained, burst capacity 4000.
- Query endpoints (`GET /api/v1/...`): 200 requests per second sustained, burst capacity 400.

Per Spec FR-012a, the rate limit is NOT the SLO. Feature-001 SC-002 (1000 events/s/tenant sustained at ≥99.9% success) is the system's contract to the tenant; the rate limit is the system's protection against a misbehaving tenant. The 2x SLO sustained / 4x SLO burst configuration gives every tenant their full SLO budget plus 100% headroom; the limiter fires only when a tenant is sustaining double their entitlement, which is the noisy-neighbor case (US2). The runbook page that documents these defaults MUST warn future operators against lowering the inbound default to "match the SLO" — a change which would make SLO compliance structurally unattainable.

### Part 2 — Token-bucket algorithm + Redis Lua

Each `(tenant_id, endpoint)` pair gets a Redis key `ratelimit:{tenant_id}:{endpoint}` storing two fields: `tokens` (current available tokens) and `last_refill_at` (millisecond timestamp of the last refill). The token-bucket logic runs as a single Lua script (`src/collectmind/ratelimit/token_bucket.lua`) that performs check-and-deduct atomically in one Redis round trip:

```
EVALSHA <sha1> 1 ratelimit:{tenant_id}:{endpoint} <now_ms> <sustained_rps> <burst_capacity>
```

The script:

1. Reads the current `tokens` and `last_refill_at` (0 if absent).
2. Computes `refill = min(burst_capacity, tokens + (now_ms - last_refill_at) * sustained_rps / 1000)`.
3. If `refill >= 1`, decrements by 1, writes `tokens = refill - 1`, `last_refill_at = now_ms`, returns `(1, floor(refill - 1))` (allow, remaining).
4. Otherwise writes `last_refill_at = now_ms`, `tokens = refill` and returns `(0, retry_after_ms)` (reject, retry hint).

The script's return value drives the middleware: 1 → allow; 0 → respond with 429 + `Retry-After: ceil(retry_after_ms / 1000)`.

Latency budget: one Redis round trip + JSON marshaling. Measured locally at p99 < 1 ms; SC-005's 10% latency-regression budget is honored trivially.

### Part 3 — Failure-closed posture under Redis unavailability

When the Lua script fails (Redis connection refused, timeout > 1 s, Redis MOVED/ASK redirection during cluster failover, Lua script eviction), the rate-limit middleware MUST respond with `503 Service Unavailable` carrying `Retry-After: 1`. The middleware MUST NOT silently allow the request.

Justification: the rate limit is a security primitive. Failing open under Redis outage lets a noisy tenant escape detection precisely when the operator most needs the gate to hold. Postgres + Kafka + the validator pipeline would absorb the full request rate during the Redis outage, violating US2's "single noisy tenant cannot degrade other tenants" property. A 503 is loud and visible (the operator sees `collectmind_ratelimit_redis_unavailable_total{endpoint}` increment + an alert fires); a silent-allow is invisible.

This is the explicit deviation from the most common rate-limiter convention (fail-open during outages to preserve availability). The constitution's Principle IX bias toward security over convenience justifies the deviation.

### Part 4 — Postgres `tenant_config` for overrides, LISTEN/NOTIFY for reload

Per Spec FR-013 + the clarify-session-2026-05-11 decision, per-tenant overrides live in Postgres `tenant_config` colocated with the audit chain. The `tenant_config` write produces a `kind=tenant_config_change` audit row in the same database transaction (Spec FR-013b); a failing audit-write rolls back the configuration write.

The orchestration-api reads the configuration through an in-process LRU cache (size: 1024 tenants, sufficient for the largest expected operating fleet) with a 5-second TTL. A background asyncio task subscribes to Postgres `LISTEN tenant_config_changed`; the migration ships a trigger that emits `NOTIFY tenant_config_changed, '<tenant_id>'` after every `INSERT`/`UPDATE`/`DELETE`. On NOTIFY, the cache invalidates the named tenant's entry; the next request from that tenant fetches the new value within the next round trip.

The 5-second TTL is the safety net for NOTIFY pipeline failures (asyncpg reconnect, Postgres `pg_listen` backlog overflow). The combination is the standard "push + pull fallback" pattern: NOTIFY for sub-second responsiveness, TTL as the worst-case guarantee.

### Part 5 — Hot-store key migration mechanism: TTL-driven natural rollover

Per research §2 the hot-store key shape transitions from `vehicle_id:signal_name` to `tenant_id:vehicle_id:signal_name` via **TTL-driven natural rollover** (option C):

1. At deploy cutover, every writer immediately switches to the new tenant-scoped key shape.
2. Every reader prefers the new key; on cache miss the reader falls back to reading the legacy key.
3. Legacy keys expire naturally at the existing 24-hour TTL.
4. After 24 hours, a follow-up commit removes the fallback-read branch and asserts no legacy-shape keys remain (one-time `SCAN` + `LEN` check).

**Why TTL-driven rollover, not one-shot scripted migration**:

Under SC-002's sustained 1000 events/s/tenant, the warm working set in the hot store is ~10⁵ keys per tenant. A one-shot `SCAN`-based migration would walk ~10⁵–10⁶ keys per tenant while the system is ingesting at full rate; the per-key `RENAME` operation under contention would impose latency spikes well outside the SC-006 10 ms p95 ceiling. TTL-driven rollover has zero migration latency cost; readers absorb at most one extra `GET` on cache miss for the 24-hour fallback window.

**Why not dual-write (option B)**:

Dual-write doubles the write rate during the rollover window. The hot store is dominated by writes (telemetry ingest matches SC-002; reads are episodic feedback-worker queries). Doubling writes is worse than doubling reads under this load shape; the asymmetry makes (C) clearly cheaper than (B).

**Why the legacy TTL is short enough**:

Feature-001's TTL is 24 hours; production rollouts deploy across regions over hours-to-days, so the 24-hour fallback-read window is naturally covered by the rollout itself. The fallback-read overhead is bounded to 24 hours and tested explicitly by `tests/integration/test_hot_store_key_rollover.py`.

### Part 6 — Metric label conventions

Every new metric carries `tenant_id` only when (a) the value is derived from a verified JWT, AND (b) emitting the label cannot widen a side-channel for cross-tenant existence checks. Specifically:

- `collectmind_ratelimit_decision_total{tenant_id, endpoint, decision}` carries `tenant_id` (verified JWT-derived) and `decision in {allow, reject}`.
- `collectmind_cross_tenant_access_attempt_total{endpoint}` does NOT carry the *targeted* tenant identifier; only the endpoint. The requesting tenant's identifier is in the structured log, not the metric, to honor Spec FR-009.
- `collectmind_break_glass_total{operator_subject, reason_code}` carries the operator subject (operator JWT-derived, not tenant) and the reason code. NOT the tenant scope queried (that's in the audit row).
- `collectmind_tenant_config_change_total{tenant_id}` carries the target tenant identifier (operator-side metric; not exposed to tenants).
- `collectmind_deployment_rejected_total{reason}` carries the reason (e.g., `tenant_mismatch`) but NOT the target vehicle id or the offending tenant identifier; the audit row carries those.
- `collectmind_ratelimit_redis_unavailable_total{endpoint}` carries the endpoint.

Cardinality concern: 10⁴ tenants × 10 endpoints × 2 decisions = 2 × 10⁵ time series on `collectmind_ratelimit_decision_total`. A single Prometheus instance handles that comfortably (~10⁶ time series is the documented practical limit). If the deployed tenant count climbs past 10⁵, switch to a Prometheus-remote-write to a long-term store (Mimir or similar); that's a future-feature decision, not this ADR's scope.

## Consequences

### Positive

- Rate-limit overhead is one Redis round trip; SC-005 (latency budget preserved within 10%) is honored with significant margin.
- Failure-closed posture under Redis outage prevents a class of "rate limit silently disabled while operator believes it's enforced" incidents.
- LISTEN/NOTIFY-driven config reload gives sub-second responsiveness for operator overrides; the TTL fallback covers NOTIFY-pipeline failures.
- TTL-driven hot-store rollover has zero migration-time wall-clock cost. The Redis migration cannot cause an SC-006 violation by construction (there is no migration step that touches Redis under load).
- The atomic-audit pattern (`tenant_config` write + `kind=tenant_config_change` audit row in same transaction) reuses the same shape as ADR-0007's break-glass primitive; one mental model, two applications.

### Negative

- Failure-closed under Redis outage means a Redis outage temporarily takes the inbound and query APIs offline. The runbook page for `RatelimitRedisUnavailable` MUST describe the failover procedure (route around the failed primary; restart the orchestration-api containers if the Redis cluster has been restored but connection pools are stale). This is a real availability trade; it's the right trade per the security argument, but operators must be trained.
- The 24-hour TTL-driven rollover window means the fallback-read branch lives in the codebase for the rollover period plus a one-time-cleanup PR. The branch is small (one `if`), but it's a code-debt item with a defined sunset.
- High-cardinality metric labels (`tenant_id` on rate-limit decisions) scale linearly with tenant count. At 10⁵+ tenants, a Prometheus remote-write target is required; the runbook records this scaling boundary.

### Neutral

- The Lua script is byte-pinned at the orchestration-api build (the SHA1 is embedded in `metrics.py` + verified at startup). Lua script eviction triggers a re-load, which is transparent. Re-load contention under outage is treated as a Redis-unavailable case and follows the failure-closed posture.

## Alternatives considered

### Postgres-backed token-bucket counters (in `tenant_config` or a separate `ratelimit_counters` table)

Rejected. Write amplification: every authenticated request would issue an `UPDATE ... RETURNING` against a per-tenant row in Postgres, which at SC-002's 1000 events/s/tenant rate is ~10⁶ writes/minute per tenant. Postgres can absorb this with the right index posture, but it costs significantly more CPU than Redis and competes with the audit-write workload. Redis is the right tool for transient per-request counters.

### Sliding-window rate limiter (instead of token-bucket)

Considered. Token-bucket is simpler, supports burst capacity naturally, and is well-understood by operators. Sliding-window gives a smoother rate calculation but at the cost of more complex Lua and more state per key. The simplicity argument wins; token-bucket is the standard pattern for this use case.

### Failure-open under Redis outage (the conventional choice)

Rejected per Part 3. The constitutional Principle IX bias toward security over convenience justifies the deviation from convention.

### One-shot scripted hot-store migration (research §2 option A)

Rejected per the SC-006 contention argument in Part 5.

### Dual-write hot-store migration (research §2 option B)

Rejected per the write-amplification argument in Part 5.

### A new `ratelimit_overrides` table separate from `tenant_config`

Considered. `tenant_config` already carries per-tenant configuration; splitting rate-limit overrides into a separate table would create two parallel "override" surfaces with different operator workflows. Rejected as over-decomposition.

### `pg_cron` or a managed scheduler for cache reload

Rejected. LISTEN/NOTIFY is event-driven; a scheduler-based approach would introduce polling latency. The asyncpg `add_listener` API is already present in the project's dependency set; reuse beats new infrastructure.

## References

- [`specs/002-multi-tenant-isolation/spec.md`](../../specs/002-multi-tenant-isolation/spec.md) §Clarifications Q2, FR-010 through FR-017
- [`specs/002-multi-tenant-isolation/research.md`](../../specs/002-multi-tenant-isolation/research.md) §2, §5a, §5b, §5c, §5d
- [`specs/002-multi-tenant-isolation/data-model.md`](../../specs/002-multi-tenant-isolation/data-model.md) §New table: `tenant_config`
- ADR-0007 (RLS + break-glass) for the atomic-audit pattern that `tenant_config_change` mirrors
- Constitutional principles IX, XI, XVII at [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
- Feature-001 SC-002 (sustained ingest), SC-006 (hot-store read latency) at [`specs/001-policy-loop-vertical-slice/spec.md`](../../specs/001-policy-loop-vertical-slice/spec.md)
