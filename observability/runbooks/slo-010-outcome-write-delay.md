# SC-010 — Outcome write delay p95 > 5 minutes

Alert: `OutcomeWriteDelayBreach`. Constitution Principle XI binding SLO.

## Symptoms

- `histogram_quantile(0.95, sum(rate(collectmind_policy_outcome_write_delay_seconds_bucket[15m])) by (le))` > 300 for ≥ 5 min.
- Dashboard "Outcome write delay p95 (SC-010)" (panel 14) shows the bar above the 5-minute mark.

## Dashboard

- Grafana → CollectMind End-to-End → "Outcome write delay p95 (SC-010)" (panel 14).
- Correlate with `slo-005-recovery.md` if the system was recently in outage recovery.

## Mitigation

1. Inspect the feedback worker's tick loop in Loki for `feedback_tick_error`.
2. Check `deployment_targets` row count where `status='accepted' AND expires_at <= now()`; a large backlog means the worker is falling behind.
3. Confirm the `TIME_ACCELERATION_FACTOR` env var is set as expected. If a soak run has dropped to factor=1 while production code expects 10000, every window stays open for its full 168 hours.
4. Restart the feedback worker if no explicit error appears.

## Escalation

- 30 minutes without recovery: page the platform on-call. Outcome write delay is the customer-visible signal that the policy loop is broken.

## Related ADRs

- (none.)

## Related FRs

- FR-009 — feedback evaluation after window close.
- FR-009a — logical-time scheduling.
- SC-010 — outcome write delay SLO.
