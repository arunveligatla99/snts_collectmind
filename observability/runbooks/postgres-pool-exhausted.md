# Postgres connection pool saturated

## Symptoms

- `asyncpg` `TooManyConnectionsError` in orchestration-api logs.
- Query API p95 climbs across every route simultaneously.

## Dashboard

- Grafana → CollectMind End-to-End → "Query latency p95 (SC-004)" (panel 13).
- Postgres exporter (if present): `pg_stat_activity_count`, `pg_settings_max_connections`.

## Mitigation

1. Inspect `pg_stat_activity` for long-running transactions; kill obvious offenders.
2. Restart the orchestration-api to release leaked connections.
3. If the load is legitimate: increase the pool's `max_size` in `src/collectmind/registry/db.py` and the RDS `max_connections` parameter.

## Escalation

Page the database on-call after 10 minutes without recovery.

## Related ADRs

- (none.)

## Related FRs

- FR-010 — query interface; FR-014 — observability.
