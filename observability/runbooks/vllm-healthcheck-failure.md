# vLLM /health failing

## Symptoms

- `curl http://slm-inference:8000/health` returns non-200 or times out.
- `slm_generation_latency_seconds` shows long tails or no samples.

## Dashboard

- Grafana → CollectMind End-to-End → "SLM generation latency p95" (panel 9).

## Mitigation

1. Check container logs for FSM compilation errors, NCCL errors, or CUDA OOM.
2. Verify GPU presence inside the container: `docker compose exec slm-inference nvidia-smi`.
3. If FSM compilation is slow on first request, ensure the warm-up fixture has run (per FR-022 SLM contract test policy).
4. Restart the container; weights remain cached on the host volume.

## Escalation

Page the SLM platform on-call. Failover to the CPU profile per `cpu-fallback-activation.md` if recovery exceeds 10 minutes.

## Related ADRs

- [ADR-0002](../../docs/adr/0002-default-slm-qwen2-5-7b-instruct.md), [ADR-0003](../../docs/adr/0003-constrained-decoding-library.md).

## Related FRs

- FR-014 — SLM latency metric.
