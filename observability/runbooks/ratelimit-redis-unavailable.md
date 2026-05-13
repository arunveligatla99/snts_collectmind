# Runbook: Rate-limit Redis unavailable

**Alert**: `RatelimitRedisUnavailable` (page-tier)
**SLO anchor**: ADR-0008 Part 3 (failure-CLOSED posture under Redis outage)
**Related FRs**: FR-010, FR-011, FR-017

## Symptoms

- `collectmind_ratelimit_redis_unavailable_total{endpoint}` counter is incrementing for one or more endpoints.
- Clients see `503 Service Unavailable` with `Retry-After: 1` instead of the usual 202/200/429 mix.
- Orchestration-api logs show structured events with `event=ratelimit_redis_unavailable` and a `redis.exceptions.ConnectionError` (or similar) as the underlying error.
- Possibly: the `redis-health-check` (Phase 4) is also red.

This is the failure-CLOSED posture from ADR-0008 Part 3. The rate-limit middleware is rejecting every request rather than silently allowing them through. **This is by design** — the limiter is a security primitive; failing open would let a noisy tenant escape detection precisely when the operator most needs the gate to hold.

## Dashboard

Grafana dashboard `CollectMind end-to-end` → row **Per-tenant rate limiting**:

- Panel **Redis-unavailable rate by endpoint** — `rate(collectmind_ratelimit_redis_unavailable_total[1m])`. Confirms the failure-mode is "Redis is down", NOT "the rate limit is being hit" (which would be on the `_throttled_total` panel).
- Panel **Redis cluster health** — `up{job="redis"}`. If 0, the Redis instance is unreachable to Prometheus too.

## Mitigation

1. **Confirm Redis is reachable**:
   ```
   redis-cli -h <redis-host> -p 6379 PING
   ```
   If PONG: the orchestration-api's client may have stale connections; restart the orchestration-api container(s) to force fresh connections.

   If no response: investigate the Redis cluster (see Escalation below).

2. **Check ElastiCache console** (cloud) or **Compose container state** (local):
   ```
   docker compose -f infra/compose/docker-compose.yaml ps redis
   ```

3. **Verify the Lua script is loaded** (in case Redis was restarted and the script cache was lost — the middleware re-loads on NOSCRIPT, but a flap can hit a window where the SHA is stale):
   ```
   redis-cli -h <redis-host> SCRIPT EXISTS <sha>
   ```
   Returns `(integer) 1` if loaded; the middleware auto-reloads on NOSCRIPT.

## Escalation

- **Sustained outage** (> 5 minutes): page the on-call platform engineer. The orchestration-api is rejecting every authenticated request with 503; tenants are seeing service degradation.
- **Redis cluster failover** (MOVED/ASK errors in logs): expected during a failover; the middleware retries on the next request. If the failover takes > 30 seconds, page.
- **NOSCRIPT loop** (orchestration-api keeps re-loading the Lua script): possible Redis-side script eviction policy issue. Investigate Redis memory pressure + script-cache size.

## Why is the limiter failing closed and not open?

Per ADR-0008 Part 3, the rate limit is a **security primitive**. Failing open during a Redis outage lets a noisy tenant escape detection precisely when the operator most needs the gate to hold. Postgres + Kafka + the validator pipeline would absorb the full request rate during the Redis outage, violating US2's "single noisy tenant cannot degrade other tenants" property. A 503 is loud and visible (operators see this alert); a silent-allow would be invisible.

This IS the explicit deviation from the most common rate-limiter convention. Constitution Principle IX (security over convenience) justifies it. **Do not change the posture to fail-open** without a constitution amendment + ADR.

## Related ADRs

- [ADR-0008 Part 3](../../docs/adr/0008-per-tenant-rate-limiting.md#part-3--failure-closed-posture-under-redis-unavailability) — failure-closed posture.

## Related FRs

- FR-010 (per-tenant rate limit).
- FR-017 (auth runs before limiter; auth-failure must not advance counters — but Redis-unavailable here means SOMETHING ELSE has happened: every request is failing the limiter, including authenticated ones).
