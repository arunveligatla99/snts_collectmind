# Kafka consumer-group lag elevated

## Symptoms

- `kafka_consumergroup_lag` (or the equivalent JMX export) exceeds the per-topic threshold for ≥ 5 min.
- Pipeline funnel shows `received` growing while `generated` stagnates.

## Dashboard

- Grafana → CollectMind End-to-End → "Generation funnel" (panel 2).
- Drill: `kafka-consumer-groups.sh --bootstrap-server localhost:29092 --describe --group collectmind-ingest`.

## Mitigation

1. Scale the consumer (`ingest-worker`) horizontally.
2. Confirm the broker is not network-partitioned: `kafka-broker-api-versions.sh`.
3. Check for stuck transactions / abandoned consumer-group members.

## Escalation

Page the platform on-call. Lag without convergence after a scale-out indicates a downstream bottleneck (Postgres, Redis, or the SLM).

## Related ADRs

- (none.)

## Related FRs

- FR-022a — recovery-from-outage drain.
