# SC-012 — Orchestration-API availability < 99.9% monthly

Alert: `AvailabilityBreach`. Constitution Principle XI binding SLO.

## Symptoms

- `avg_over_time(up{job="orchestration-api"}[10m])` < 0.999 for ≥ 5 min.
- External monitoring shows 5xx responses or refused connections from the orchestration-api.

## Dashboard

- Grafana → CollectMind End-to-End → header status pane.
- Per-route status_class breakdown: `sum by (status_class, route) (rate(collectmind_http_request_total[5m]))`.

## Mitigation

1. Identify whether the breach is one container down or many: `docker compose ps orchestration-api`.
2. Inspect the container logs for OOM kills: `journalctl -u docker` and `docker inspect`.
3. Check downstream health: Postgres pool exhaustion (`postgres-pool-exhausted.md`), Redis evictions (`redis-evictions.md`), Kafka broker availability.
4. Confirm the auth surface: an OAuth2 issuer outage (`oauth2-issuer-unavailable.md`) shows here as a 5xx tail even if the API is healthy.

## Escalation

- Per the SC-012 monthly budget (~43 min/month), every minute matters. Page the platform on-call immediately on a sustained breach.

## Related ADRs

- [ADR-0005](../../docs/adr/0005-slm-hosting-topology.md) — capacity planning.

## Related FRs

- FR-018 — authentication on every external endpoint.
- SC-012 — availability SLO.
