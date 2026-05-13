# SC-006 — Dashboard metric staleness > 10s

Alert: `DashboardLagBreach`. Constitution Principle XI binding SLO. FR-015 is the contract.

## Symptoms

- `time() - max(timestamp(collectmind_diagnostic_findings_received_total))` > 10 for ≥ 1 min.
- On-call opens the dashboard and panels show stale data despite ingest activity.

## Dashboard

- Grafana → CollectMind End-to-End → top header refresh indicator.
- Confirm the dashboard's auto-refresh is set to 5 s (the JSON pin).

## Mitigation

1. Verify Prometheus is scraping the orchestration-api job: `curl http://localhost:9090/api/v1/targets`.
2. Verify the `/metrics` endpoint on the orchestration-api is reachable from inside the Prometheus container: `docker compose exec prometheus wget -qO- http://orchestration-api:8000/metrics | head -5`.
3. Confirm `infra/compose/prometheus.yml` has `scrape_interval: 2s`; a regression to the original 15s value violates SC-006 by construction.
4. If Prometheus itself is slow, check its rule-evaluation backlog: `prometheus_rule_evaluation_duration_seconds`.

## Escalation

- 5 minutes without recovery: page the platform on-call; dashboard lag during an incident is its own incident.

## Related ADRs

- (none.)

## Related FRs

- FR-015 — operator dashboard with at most 10s lag.
- SC-006 — binding dashboard-lag SLO.

## Measured steady-state (T136, 2026-05-11)

| Metric | Value |
|---|---|
| Sample size | 5 publications |
| Max ingest-to-Prometheus visibility | **2.11 s** |
| Mean | 1.98 s |
| SC-006 budget | 10 s |
| Verdict | **PASS** (~5× headroom against the ceiling) |

Methodology: snapshot the per-tenant counter, publish a finding through `POST /api/v1/findings`, poll the Prometheus instant-query API every 200 ms until the counter rises, record elapsed wall time. Repeated five times with a 2 s gap between runs. The 2 s steady-state floor matches the configured `scrape_interval` in `infra/compose/prometheus.yml` (T114 lowered this from 15 s to 2 s exactly so SC-006 is honored by construction).
