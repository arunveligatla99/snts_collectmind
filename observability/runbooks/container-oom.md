# Generic container OOM

## Symptoms

- Any application container exits with status 137 (OOMKilled).
- Affected service drops out of Prometheus targets (`up == 0`).

## Dashboard

- Grafana → CollectMind End-to-End → header status indicator (drives `AvailabilityBreach`).

## Mitigation

1. `docker inspect <container>` and read `State.OOMKilled`.
2. Compare `process_resident_memory_bytes` against the container's memory limit; raise the limit only after profiling.
3. Look for unbounded structlog or queue accumulation in the service's logs.

## Escalation

Repeated OOMs require an engineering fix, not just a runtime tweak.

## Related ADRs

- (none.)

## Related FRs

- Constitution Principle V — observability.
