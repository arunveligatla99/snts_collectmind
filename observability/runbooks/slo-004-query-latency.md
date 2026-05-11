# SC-004 — Query API p95 > 200ms

Alert: `QueryLatencyBreach`. Constitution Principle XI binding SLO.

## Symptoms

- `histogram_quantile(0.95, sum(rate(collectmind_query_request_latency_seconds_bucket[5m])) by (le))` > 0.2 for ≥ 5 min.
- Dashboard "Query latency p95 (SC-004)" (panel 13) shows the offending route(s).

## Dashboard

- Grafana → CollectMind End-to-End → "Query latency p95 (SC-004)" (panel 13). Each query route reports its own histogram.
- Correlate with `postgres-pool-exhausted.md` if multiple routes are slow simultaneously.

## Mitigation

1. Inspect the slow route's PostgreSQL plan: `EXPLAIN ANALYZE` against the query in `src/collectmind/registry/repository.py`.
2. Check `pg_stat_activity` for long-running transactions and pool saturation.
3. Verify the GIN indexes from migrations `004_collection_policies.sql` and `007_policy_outcomes.sql` are present and being used.
4. If RLS overhead dominates, confirm `tenant_id` is set on every transaction (per `src/collectmind/registry/db.py`).

## Escalation

- 10 minutes without recovery: page the database on-call.

## Related ADRs

- (none — query API is deterministic Python on RDS Postgres+Timescale.)

## Related FRs

- FR-010 — query interface.
- SC-004 — query latency SLO.
