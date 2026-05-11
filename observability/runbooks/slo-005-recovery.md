# SC-005 — Recovery from outage exceeded 5 minutes

Alert: `RecoveryFromOutageBreach`. Constitution Principle XI binding SLO. FR-022a is the contract.

## Symptoms

- `rate(diagnostic_findings_received_total) - rate(policy_outcome_total)` stays > 0.1/s for ≥ 5 min.
- Operator dashboard "Generation funnel" panel shows ingest continuing but outcomes failing to drain.

## Dashboard

- Grafana → CollectMind End-to-End → "Generation funnel" (panel 2).
- Correlate with "Dead-letter count" (panel 6); a non-empty DLQ during recovery means events are being routed to the dead-letter queue rather than draining.

## Mitigation

1. Confirm every internal dependency is reachable: Postgres, Redis, Kafka, the SLM container, the mock-issuer.
2. If a recent dependency restart is the cause, watch the Kafka consumer-group lag for `diagnostic-findings.v1` and `vehicle-telemetry.v1`; lag should fall steadily.
3. If the lag is flat or rising, the feedback worker has stalled — check the `feedback_tick_error` log entries in Loki.
4. As a last resort, restart the orchestration-api container; the LangGraph runner is stateless after a successful audit write.

## Escalation

- 10 minutes without recovery: declare an incident. Backlogged events that fail to drain inside the SC-005 budget are an FR-022a violation and trigger a customer-facing communication.

## Related ADRs

- [ADR-0006](../../docs/adr/0006-dev-default-policy-client.md) — dev_default path under the SC-005 contract.

## Related FRs

- FR-022a — recovery-from-outage contract.
- SC-005 — binding recovery SLO.
