# SC-002 — Sustained ingest success rate < 99.9%

Alert: `SustainedIngestSuccessRateBreach`. Constitution Principle XI binding SLO.

## Symptoms

- `sum(rate(collectmind_policy_deployed_total[10m])) / sum(rate(collectmind_diagnostic_findings_received_total[10m]))` < 0.999 for ≥ 10 min.
- Operator dashboard "Generation funnel" panel shows the `deployed` trace diverging from `received` while the system is under load.

## Dashboard

- Grafana → CollectMind End-to-End → "Generation funnel" (panel 2).
- Correlate with "Dead-letter count" (panel 6); a rising DLQ explains most failures.

## Mitigation

1. Drill into `policy-deployments.v1` consumer lag (per the Kafka exporter).
2. Inspect dead-letter contents: `kafka-console-consumer --topic policy-deployments.v1.dlq`.
3. If validation failures dominate, check `slm-weight-digest-mismatch.md` and `vllm-healthcheck-failure.md`.
4. If deployer failures dominate, check the simulated CollectorAI's failure-injection setting; in production, check the real Collector AI's status page.

## Escalation

- 20 minutes without recovery: page the platform on-call and the data-engineering on-call.
- Page rotation rules live in PagerDuty under service `collectmind-ingest`.

## Related ADRs

- [ADR-0004](../../docs/adr/0004-fingerprint-stub.md) — deterministic stub used for load testing.
- [ADR-0005](../../docs/adr/0005-slm-hosting-topology.md) — capacity planning.

## Related FRs

- FR-008 — deliver validated policy to downstream.
- FR-014 — generation funnel metrics.
- SC-002 — sustained ingest success rate SLO.
