# SC-001 — End-to-end policy-deploy latency p95 > 12s

Alert: `E2ELatencyBreach`. Constitution Principle XI binding SLO.

## Symptoms

- `histogram_quantile(0.95, ...time_to_deploy_seconds_bucket...)` exceeds 12 s for ≥ 5 min.
- Operator dashboard "Time-to-deploy (p50/p95/p99)" panel shows the p95 trace above the 12-second mark.
- Findings still flow through ingest; deployment records still land; only the wall-clock latency is wrong.

## Dashboard

- Grafana → CollectMind End-to-End → "Time-to-deploy (p50/p95/p99)" (panel 4).
- Correlate with "SLM generation latency p95" (panel 9) and "Validation pass rate" (panel 3); a high SLM latency or a retry storm via panel 7 explains most regressions.

## Mitigation

1. Check the SLM container: `docker compose ps slm-inference` (or the ECS service). If unhealthy, restart and watch `/info` come back.
2. Inspect retry rate (panel 7); a non-zero retry rate means the validator is rejecting generations and the orchestrator is paying the retry tax. Drill into the most recent `rejected` audit events at `GET /api/v1/audit/{correlation_id}` to see the validation errors.
3. Confirm the active SLM weight SHA matches the manifest (panel 11). A mismatch indicates a startup or rollback in flight.
4. If SLM latency is fine but the end-to-end histogram is elevated, profile the validator and the deployer; both are deterministic Python and should add < 200 ms each.

## Escalation

- 15 minutes without recovery: page the SLM platform on-call; consider failing over to the CPU profile per `cpu-fallback-activation.md`.
- 30 minutes without recovery: declare an incident and freeze new deployments at the orchestration-api ingress.

## Related ADRs

- [ADR-0002](../../docs/adr/0002-default-slm-qwen2-5-7b-instruct.md) — default SLM choice and upgrade/rollback procedure.
- [ADR-0003](../../docs/adr/0003-constrained-decoding-library.md) — constrained-decoding library; retry storms often surface as constraint violations.
- [ADR-0005](../../docs/adr/0005-slm-hosting-topology.md) — GPU node-group capacity is the most common root cause for sustained latency regressions.

## Related FRs

- FR-014 — generation funnel + time-to-deploy distribution.
- FR-022 — runbook entry per alert.
- SC-001 — binding latency SLO.
