# SLM weight SHA-256 verification fails at start

## Symptoms

- Readiness probe fails closed; SLM container logs `weight digest mismatch`.
- `collectmind_slm_weight_sha_active` reports `unknown` or no series.

## Dashboard

- Grafana → CollectMind End-to-End → "Active SLM weight SHA" (panel 11).

## Mitigation

1. Compare the on-disk weight directory's SHA-256 against `config/slm/qwen2.5-7b-instruct/manifest.sha256`.
2. If the manifest is correct but the disk is corrupt: re-run `scripts/fetch_qwen2.5_weights.py` to restage the weights.
3. If the manifest itself is stale (an intentional upgrade is in flight): land an ADR per Constitution Principle XIII, then update the manifest atomically with the new weight.

## Escalation

A digest mismatch is a supply-chain signal. Treat as a P1 security event; loop in the security on-call before restarting.

## Related ADRs

- [ADR-0002](../../docs/adr/0002-default-slm-qwen2-5-7b-instruct.md).

## Related FRs

- Constitution Principle IX — model weights as supply-chain artifacts.
