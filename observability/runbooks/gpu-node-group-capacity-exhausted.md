# GPU node group capacity exhausted

## Symptoms

- ECS task placement failures with `RESOURCE:GPU` insufficient capacity.
- Pending pods/tasks; SLM scale-out events fail.

## Dashboard

- AWS console → ECS → Capacity Providers → ASG headroom.
- Grafana → CollectMind End-to-End → "Active SLM runtime image digest" (panel 12) shows runtime degraded to CPU.

## Mitigation

1. Increase the ASG `desired_capacity`; verify the corresponding `g5.2xlarge` quota in the region.
2. If quota is the bottleneck: file a quota increase with AWS Support (lead time ~24h).
3. As a temporary measure, fail traffic over to the CPU profile per `cpu-fallback-activation.md`.

## Escalation

Page the platform on-call and AWS TAM. A persistent shortage is a capacity-planning incident.

## Related ADRs

- [ADR-0005](../../docs/adr/0005-slm-hosting-topology.md).

## Related FRs

- SC-002 — sustained ingest SLO.
