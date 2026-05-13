# Tenant configuration LISTEN/NOTIFY consumer stalled

Alert: `TenantConfigReloadStalled`. SC-014 page. Constitution Principle V (Observability Is a Functional Requirement); ADR-0008; Spec FR-013 / FR-013a / FR-013b.

Fires when the orchestration-api's `tenant_config` cache consumer has not applied a Postgres `NOTIFY tenant_config_changed` event within 5 seconds for 2 minutes. The cache holds per-tenant rate-limit overrides (FR-013); stale cache means rate-limit decisions use outdated ceilings.

## Symptoms

- `TenantConfigReloadStalled` alert firing with `severity=page`, `slo=SC-014`.
- `collectmind_tenant_config_cache_consumer_lag_seconds` gauge shows a value > 5.
- A service-principal write against `tenant_config` lands in Postgres (verifiable via the matching `kind=tenant_config_change` audit row per FR-013b atomic-audit) but the rate-limit middleware continues to apply the prior ceiling for the affected tenant.
- Operator dashboard "tenant_config consumer lag" panel (if present per T281 / Phase 14 polish) shows the gauge above 5 s.

## Dashboard

- Grafana → CollectMind End-to-End → "tenant_config consumer lag" panel.
- Cross-reference the `audit_events` table for the most-recent `kind=tenant_config_change` row's `occurred_at` timestamp versus the `tenant_config_cache_consumer_lag_seconds` gauge value at the same wall time.
- Inspect the orchestration-api logs for `tenant_config_cache_listen_loop` errors; the consumer is implemented as a long-running `LISTEN`-loop in `src/collectmind/ratelimit/config_cache.py`.

## Mitigation

1. **Verify Postgres `LISTEN/NOTIFY` is operational**: `docker exec collectmind-postgres psql -U collectmind -d collectmind -c "SELECT pg_notify('tenant_config_changed', 'manual-test');"` from the operator host. The orchestration-api should log `tenant_config_cache_notification_received` within 1 second.
2. **If no notification is received** by the orchestration-api: the `LISTEN` connection has dropped. Restart the orchestration-api container; the lifespan handler re-establishes the listener (`TenantConfigCacheConsumer.start()`). Watch for `tenant_config_cache_started` in the startup logs.
3. **If notification is received but the cache does not refresh**: the consumer-side apply path has a bug. Inspect logs for `tenant_config_cache_apply_failed`; the most likely cause is a Postgres connection failure in the apply path (the consumer holds a separate connection from the LISTEN connection per ADR-0008).
4. **If the alert is firing but the gauge is incorrect** (the cache is up-to-date but the lag metric is wrong): the metric emission path has a regression. The gauge is updated in `TenantConfigCacheConsumer._apply_refresh()`; verify the gauge is being set on every successful apply.
5. **Immediate operational impact mitigation**: while the consumer is stalled, any new `tenant_config` overrides are not honored. If a tenant needs an override applied immediately (e.g., to raise rate-limit for an incident response), bounce the orchestration-api container — the cache rebuilds from Postgres on startup. This is a heavy hammer; use only when the operator workflow cannot wait.

## Escalation

- Lag > 5 s for 2 min (alert threshold): page on-call.
- Lag > 30 s for 5 min: the consumer is structurally broken (not just lagging). Escalate to the platform on-call; rate-limit middleware decisions are increasingly stale.
- Lag > 5 min: declare a Sev-2 incident. Recent `tenant_config_change` audit rows have not been applied; production tenants may be over- or under-throttled relative to their configured ceilings.
- Alert clears spontaneously after firing for < 5 min: a transient Postgres restart or network blip. Document the event but no further action required if no `tenant_config_change` audit rows landed during the stall window. If rows DID land, manually verify each was applied (the gauge says yes after recovery, but spot-check via a `GET /api/v1/tenant-config/self` from a tenant principal).

## Related ADRs

- [ADR-0008](../../docs/adr/0008-rate-limiting-and-hot-store-migration.md) — rate-limit middleware + `tenant_config` LISTEN/NOTIFY consumer.

## Related FRs

- FR-013 — `tenant_config` persistence + reloadable via short-TTL cache.
- FR-013a — RLS on `tenant_config` (tenant-scoped SELECT; service-principal-only writes).
- FR-013b — atomic-audit row per write.
- SC-014 — `tenant_config` writes produce matching `kind=tenant_config_change` audit row.
