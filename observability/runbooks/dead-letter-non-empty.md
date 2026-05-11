# Dead-letter queue non-empty

## Symptoms

- `collectmind_dead_letter_queue_depth` > 0.
- Findings that exhaust the retry budget land here.

## Dashboard

- Grafana → CollectMind End-to-End → "Dead-letter count" (panel 6).

## Mitigation

1. Query the audit trail for the affected `correlation_id`s: `GET /api/v1/audit/{correlation_id}` returns the rejection events with `error.details.validation_errors`.
2. Group by failure cause; common causes: VSS-invalid signal names, schema-version mismatch, oversize collection windows.
3. If the root cause is upstream (a misbehaving simulator or upstream service), fix the source; the dead-letter rows themselves are diagnostic, not retryable.

## Escalation

Treat any sustained dead-letter activity as a P3 ticket; depth above 10% of ingest rate as a P2.

## Related ADRs

- (none.)

## Related FRs

- FR-006 — reject non-VSS signals; FR-003a — schema-version handling.
