# Runbook: Sustained per-tenant rate-limit throttling

**Alert**: `RatelimitSustainedThrottle` (page-tier)
**SLO anchor**: FR-016 (page when any tenant is throttled continuously beyond a configured duration)
**Related FRs**: FR-010, FR-011, FR-012, FR-012a
**Related ADRs**: ADR-0008

## Symptoms

- One tenant's traffic to `POST /api/v1/findings` (or `GET /api/v1/...`) gets a sustained run of `429 Too Many Requests` responses with `Retry-After` headers.
- The `collectmind_ratelimit_throttled_total{tenant_id, endpoint}` counter is incrementing for the named tenant + endpoint.
- The `collectmind_ratelimit_decision_total{tenant_id, endpoint, decision="reject"}` series is rising for the same labels.
- Other tenants are unaffected (their `decision="allow"` rate is unchanged; their request p95 is within budget).

## Dashboard

Grafana dashboard `CollectMind end-to-end` → row **Per-tenant rate limiting**:

- Panel **Throttle rate per tenant per endpoint** — heat-map of `collectmind_ratelimit_throttled_total` rate over the last 5 minutes. Look for tenants with sustained non-zero cells.
- Panel **Allow vs reject ratio** — `sum by (tenant_id) (rate(collectmind_ratelimit_decision_total{decision="reject"}[1m])) / sum by (tenant_id) (rate(collectmind_ratelimit_decision_total[1m]))`. Confirms throttling is for one tenant, not system-wide.
- Panel **End-to-end latency p95 per tenant** — confirms US2 SC-004 holds (other tenants unaffected during the burst).

## Mitigation

1. **Confirm the tenant**: identify the tenant_id from the alert payload or dashboard panel.
2. **Confirm the burst shape**: scroll the dashboard for the last 30 minutes. Is the throttle a one-off spike (operator backfill) or a sustained pattern (misconfigured client / runaway loop)?
3. **Reach out to the tenant** via the operator-side support workflow if the burst is unexpected. The 429 + `Retry-After` response is doing its job — the limiter is protecting shared infrastructure. The page is informational unless the burst persists beyond the configured `for` duration (default 10 minutes).
4. **For a documented backfill** (the tenant warned operations in advance): raise the tenant's rate-limit override via the service-principal write primitive. The override lands in `tenant_config`; the LISTEN/NOTIFY consumer invalidates the in-process cache within 1 second.

   ```
   psql ... -c "
     INSERT INTO tenant_config (tenant_id, inbound_sustained_rps, inbound_burst_capacity,
       query_sustained_rps, query_burst_capacity, updated_by_subject)
     VALUES ('<tenant_id>', 5000, 10000, 500, 1000, 'svc-incident-<your-name>')
     ON CONFLICT (tenant_id) DO UPDATE SET ...
   "
   ```

   The write triggers a `kind=tenant_config_change` audit row in the same transaction (FR-013b / SC-014).
5. **For a runaway client**: contact the tenant; provide their `Retry-After` headers and a copy of the rate-limit panel.

## Escalation

- If the burst is consistent with a known incident or scheduled traffic surge: file an incident ticket under the appropriate severity.
- If the burst correlates with degraded downstream service (Postgres CPU, Redis CPU, Kafka backlog): page the on-call platform engineer.
- If the burst is from a tenant whose configured rate limit is below the FR-012 default: review the override row in `tenant_config`. The override may have been mis-set during a prior incident.

## Related ADRs

- [ADR-0008](../../docs/adr/0008-per-tenant-rate-limiting.md) — per-tenant rate limiting + hot-store key migration mechanism.

## Related FRs

- FR-010 (per-tenant rate limit on inbound + query endpoints).
- FR-011 (429 + Retry-After response shape).
- FR-012 (FR-012 default values).
- FR-012a (rate-limit-vs-SLO distinction).
- FR-016 (page-tier alert on sustained throttle).

---

## ⚠️ Operational note (FR-012a — DO NOT IGNORE)

**The rate limit is NOT the SLO.** Feature-001 SC-002 (1000 events/s/tenant sustained at ≥99.9% success) is what the system promises a tenant. The FR-012 rate-limit defaults (2000 r/s sustained for inbound; 200 r/s for query) are 2× the SLO floor — the limiter fires only when a tenant is sustaining DOUBLE their entitlement. Setting the rate limit equal to the SLO floor would make SLO compliance **structurally unattainable**: a tenant operating exactly at 1000 r/s sustained would hit the limiter and fail the ≥99.9% half of SC-002.

If a future operator is tempted to "lower the inbound default to match the SLO" — DO NOT. The rate limit protects shared infrastructure from misbehaving tenants; the SLO is what we promise to well-behaved tenants. Two distinct concerns, two distinct values, by design.
