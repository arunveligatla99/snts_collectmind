# SC-003 — Soak-tier error rate > 0.1% or memory growth > 5%

Alert: `SoakErrorRateOrMemoryBreach`. Constitution Principle XI binding SLO.

## Symptoms

- Authentication-failure rate + dead-letter depth exceeds 0.1% of ingest rate for ≥ 30 min during a soak run.
- `process_resident_memory_bytes{job="orchestration-api"}` shows > 5% growth over the soak window.

## Dashboard

- Grafana → CollectMind End-to-End → "Authentication-failure rate" (panel 8) + "Dead-letter count" (panel 6).
- Long-window memory growth: query `delta(process_resident_memory_bytes{job="orchestration-api"}[24h])`.

## Mitigation

1. If memory growth dominates: take a `py-spy` flamegraph of the orchestration-api container; common culprits are unbounded async queues and unbounded structlog context bindings.
2. If error-rate dominates: drill into the dead-letter queue contents and group by `kind`.
3. Confirm the SLM container is not leaking: `docker stats slm-inference` over the soak window.
4. The full SC-003 soak is `workflow_dispatch`-gated per Constitution Principle XIV; an alert here on the PR tier indicates a config drift (PR tier should never sustain a 24-hour profile).

## Escalation

- Page the SRE on-call; soak failures usually require a code change rather than a runtime intervention.

## Related ADRs

- [ADR-0002](../../docs/adr/0002-default-slm-qwen2-5-7b-instruct.md) — SLM memory profile.
- [ADR-0005](../../docs/adr/0005-slm-hosting-topology.md) — node-group sizing for soak.

## Related FRs

- FR-014 — observability metrics.
- SC-003 — 24-hour soak binding SLO.
