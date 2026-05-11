# SLM container OOM-killed

## Symptoms

- vLLM container exits with status 137; `docker ps -a` shows it as `OOMKilled`.
- Pipeline halts at the Policy Generator node; `policy_generated_total` stops incrementing.
- `time-to-deploy` p95 climbs while ingest continues.

## Dashboard

- Grafana → CollectMind End-to-End → "SLM generation latency p95" (panel 9), "Active SLM weight SHA" (panel 11), "Active SLM runtime image digest" (panel 12).

## Mitigation

1. Inspect `dmesg -T | grep -i oom`; correlate with the container PID.
2. Confirm the GPU memory budget against the configured weight quantization (per ADR-0002).
3. Reduce concurrency or batch size on the vLLM `--max-num-seqs` flag.
4. Restart the SLM container; verify readiness via `/info` and weight SHA match.

## Escalation

Page the SLM platform on-call after a single OOM event; repeated OOMs indicate capacity drift, not a transient fault.

## Related ADRs

- [ADR-0002](../../docs/adr/0002-default-slm-qwen2-5-7b-instruct.md), [ADR-0005](../../docs/adr/0005-slm-hosting-topology.md).

## Related FRs

- FR-014 — SLM observability fields.
