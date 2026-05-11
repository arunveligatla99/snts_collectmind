# SLM running on the CPU profile in a non-dev environment

## Symptoms

- `slm_runtime_image_digest_active{runtime="llama_cpp"}` reports active in a staging or production environment.
- `slm_generation_latency_seconds` p95 climbs (CPU inference is 5–20× slower than GPU).

## Dashboard

- Grafana → CollectMind End-to-End → "Active SLM runtime image digest" (panel 12).

## Mitigation

1. Identify why the GPU profile is unavailable: GPU node-group capacity (`gpu-node-group-capacity-exhausted.md`), driver mismatch, or `g5/g6` quota.
2. If the GPU profile should be available: scale the SLM Auto Scaling Group up and roll the deployment.
3. If staying on CPU is intentional (e.g., a quick-failure scenario): lower the load profile to within CPU-budget bounds.

## Escalation

Page the platform on-call. CPU-fallback in production is a P2 incident; SLOs SC-001 and SC-002 are at risk.

## Related ADRs

- [ADR-0005](../../docs/adr/0005-slm-hosting-topology.md).

## Related FRs

- Constitution Principle VI — CPU fallback profile.
