# ADR-0002: Default Small Language Model — Qwen2.5-7B-Instruct

- Status: Proposed. Promotes to Accepted when the eval-suite baseline below is filled by the follow-up commit `docs: ADR-0002 record eval baseline`.
- Gating note (T137, 2026-05-11): the closing session for feature 001 ran on a workstation without GPU access; `nvidia-smi` is not on PATH and the workflow_dispatch path that runs the real-SLM eval suite (`.github/workflows/ci-workflow-dispatch.yaml`, T120 — job `eval-suite`) requires a `[self-hosted, gpu]` runner. Per the instruction for Phase 6, no baseline numbers are fabricated; the bracketed rows below remain empty until the eval suite runs on a GPU runner. The promotion to Accepted lands in a follow-up commit at that point.
- Date: 2026-05-09
- Deciders: Arun Veligatla (project author)
- Constitutional principle: XIII (SLM-First, Isolated, Swappable Model Boundary), with downstream consequences for XIV (Deterministic, Budgeted Model Execution in CI), IX (Security, supply-chain), and XVII (Audit)

## Context

Constitutional Principle XIII (v1.0.1) requires the Policy Generator node to run an open-weight Small Language Model by default, served by a real inference runtime, with the exact Hugging Face revision SHA recorded in `research.md`. Two acceptable defaults were named: Microsoft Phi-4-mini-instruct (MIT) and Qwen2.5-7B-Instruct (Apache 2.0). The choice between them is the topic of this ADR and answers Decision D3.

The Policy Generator's job is to produce a typed `CollectionPolicySpec` JSON object given a structured diagnostic finding. This is a constrained-decoding task, not free-form generation. The model must:

1. Hold the schema reliably under grammar-constrained decoding (outlines or instructor; chosen in ADR-0003).
2. Generate semantically appropriate VSS signal selections and sampling rates given a hypothesis.
3. Run on a GPU profile (vLLM) for production-equivalent serving and on a CPU profile (llama.cpp + GGUF) for the local-quickstart fallback.
4. Be pinned by revision SHA, supply-chain-verified per Principle IX, and traceable in every audit record per Principle XVII.

Both candidates meet the open-weight and permissive-license bar. They differ on parameter count, license, architecture mainstreaming in vLLM, and recency of upstream tuning.

## Decision

**Default model: `Qwen/Qwen2.5-7B-Instruct`.**

| Field | Value |
|---|---|
| Hugging Face repo | `Qwen/Qwen2.5-7B-Instruct` |
| Revision SHA | `a09a35458c702b33eeacc393d103063234e8bc28` |
| Branch at pin time | `main` |
| Last upstream modification | 2025-01-12 |
| License | Apache-2.0 |
| Architecture | `qwen2` (mainline, no `trust_remote_code`) |
| Approximate parameters | 7 billion |
| Source URL | <https://huggingface.co/Qwen/Qwen2.5-7B-Instruct> |
| License URL | <https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/blob/main/LICENSE> |

### Inference runtime

| Profile | Runtime | Version | Quantization | Notes |
|---|---|---|---|---|
| GPU (production-equivalent) | vLLM | `v0.20.1` (released 2026-05-04, not prerelease; <https://github.com/vllm-project/vllm/releases/tag/v0.20.1>) | bf16 weights, dtype=`bfloat16` | Native Qwen2.5 weights are bf16. The vLLM image digest is pinned in `infra/compose/docker-compose.yaml` and `infra/terraform/compute/`; that digest is recorded as a separate artifact and refreshed by superseding ADR. |
| CPU fallback | llama.cpp | `b9090` (released 2026-05-09; <https://github.com/ggml-org/llama.cpp/releases/tag/b9090>) | GGUF `Q4_K_M` | Q4_K_M is the standard quality/throughput compromise for 7B models on CPU. The exact GGUF artifact is built from the pinned HF revision SHA above using the COVESA-equivalent reproducible-build pattern: source SHA in, GGUF SHA-256 out, both recorded in `config/slm/qwen2.5-7b-instruct/manifest.sha256`. |

### Decoding configuration in CI

Per Principle XIV, CI runs the real SLM under deterministic decoding:

- `temperature` = 0
- `top_p` = 1.0
- `top_k` = -1 (disabled)
- `seed` = `0xC0FFEE` (or any value pinned in `tests/contract/conftest.py`; recorded per-test and surfaced in audit records)
- Sampling configuration is identical between the GPU and CPU profiles so the contract test produces byte-identical output across runtimes for the same fingerprint.

### Supply-chain controls (Principle IX)

1. Weight artifacts are downloaded at container build time from the official Hugging Face Hub repository above, restricted to the pinned revision SHA `a09a35458c702b33eeacc393d103063234e8bc28`.
2. Each `safetensors` shard, plus `tokenizer.json`, `tokenizer_config.json`, `config.json`, `generation_config.json`, and any GGUF artifact built from them, is hashed with SHA-256 and recorded in `config/slm/qwen2.5-7b-instruct/manifest.sha256`.
3. The SLM container re-verifies every artifact at start; mismatch fails the readiness probe closed.
4. The manifest is included in the project SBOM emitted by Syft on every CI build, alongside Python dependencies.
5. Any change to the manifest requires a superseding ADR; weights are not updated by side effect of a Dockerfile rebuild.

### Audit-record fields (Principle XVII)

Every audit record produced by the Policy Generator MUST carry, in addition to the fields already mandated by the constitution:

- `slm.repo` = `"Qwen/Qwen2.5-7B-Instruct"`
- `slm.revision` = `"a09a35458c702b33eeacc393d103063234e8bc28"`
- `slm.runtime` = `"vllm"` or `"llama.cpp"`
- `slm.runtime_version` = `"v0.20.1"` or `"b9090"` (recorded as the runtime emits it)
- `slm.quantization` = `"bf16"` or `"gguf-q4_k_m"`
- `slm.decoding_seed` = the per-call seed used
- `slm.prompt_template_version` = the semver of the prompt template

### Eval-suite baseline (filled after first eval run)

The first eval-suite execution against this pinned model is the baseline. ADR-0002 reserves the following fields. They are bracketed at draft time and MUST be filled by a follow-up commit titled `docs: ADR-0002 record eval baseline` once the eval suite (RAGAS gates and golden-example contract tests) has run against the pinned SHA on the production-equivalent vLLM profile.

| Metric | Source | Target | Baseline |
|---|---|---|---|
| VSS-signal validation pass rate | Validator output over the eval corpus | 100% | `[BASELINE_VSS_PASS_RATE]` |
| `CollectionPolicySpec` schema completeness rate | Pydantic validation pass rate | 100% | `[BASELINE_SCHEMA_COMPLETENESS]` |
| Constraint-violation count per generation (constrained decoding) | outlines/instructor counter | 0 expected | `[BASELINE_CONSTRAINT_VIOLATIONS]` |
| Hypothesis-confirmation alignment with golden labels | Eval harness vs labelled fixtures | `[TARGET_CONFIRMATION_RATE]` | `[BASELINE_CONFIRMATION_RATE]` |
| Generation latency, GPU profile, batch=1, p50 | vLLM Prometheus exporter | derived to support Principle XI p95 12s end-to-end | `[BASELINE_GEN_LATENCY_P50_MS]` |
| Generation latency, GPU profile, batch=1, p95 | same | same | `[BASELINE_GEN_LATENCY_P95_MS]` |
| Generation latency, GPU profile, batch=1, p99 | same | same | `[BASELINE_GEN_LATENCY_P99_MS]` |
| Generation latency, CPU profile, batch=1, p95 | llama.cpp metric | not SLO-conformant; recorded for visibility | `[BASELINE_GEN_LATENCY_CPU_P95_MS]` |
| Wall-clock model load time, GPU profile | vLLM startup metric | `[TARGET_LOAD_TIME_GPU_S]` | `[BASELINE_LOAD_TIME_GPU_S]` |
| Wall-clock model load time, CPU profile | llama.cpp startup metric | `[TARGET_LOAD_TIME_CPU_S]` | `[BASELINE_LOAD_TIME_CPU_S]` |
| Eval-suite total runtime (workflow_dispatch full run) | CI artifact | `[TARGET_EVAL_RUNTIME_MIN]` | `[BASELINE_EVAL_RUNTIME_MIN]` |
| GPU memory footprint at idle, bf16, sequence length 4096 | nvidia-smi inside the container | `[TARGET_GPU_MEM_GB]` | `[BASELINE_GPU_MEM_GB]` |

The eval-suite golden corpus, fixtures, and labelling protocol are described in the plan output and locked in by ADR-0004 (deterministic-fingerprint stub) and the `/speckit-plan` quickstart artifact.

### Upgrade-and-rollback procedure

The model is treated as a versioned dependency with a deliberate change-control process. There is no in-place upgrade.

#### Upgrade procedure (forward)

1. **Open a superseding ADR** (e.g., `0006-default-slm-upgrade.md`). The new ADR records the prior SHA (`a09a35458c702b33eeacc393d103063234e8bc28`), the proposed new SHA, the rationale (security fix, quality improvement, license event), and links to this ADR with the line `Supersedes: ADR-0002`. This ADR's `Status` field is updated in the same PR to `Superseded by ADR-NNNN`.
2. **Run the eval suite in shadow mode** on a feature branch: spin up the proposed model at the new SHA on the GPU profile, run the full RAGAS gate suite plus the golden-example contract tests, and record the metrics in the candidate ADR's eval-baseline table.
3. **Acceptance gate**: the new SHA is acceptable only if every metric satisfies its target and no metric regresses against this ADR's baseline by more than the per-metric tolerance recorded in the eval-suite documentation. Constraint-violation count MUST be zero. VSS-signal validation pass rate MUST remain at 100%.
4. **Build and pin the new artifacts**: rebuild the SLM container against the new SHA, generate a new GGUF for the CPU profile from the same SHA, regenerate `config/slm/<repo>/manifest.sha256`, regenerate the SBOM.
5. **Promote in `infra/compose/` and `infra/terraform/`**: bump the image digest, the runtime version (if also changing), and the model SHA atomically in a single PR. The PR description MUST link to the superseding ADR and to the shadow-eval CI run.
6. **Tag a release** before merging the PR. The release tag carries the prior SHA in its release notes alongside the new one. Existing audit records continue to point at the prior SHA via the `slm.revision` audit field.
7. **Cache the prior weights**: the prior SHA's weights and GGUF artifact remain in the manifest history and in the GitHub Actions cache for a rolling 90-day window so a rollback can complete without an external network fetch.
8. **Run the deterministic-fingerprint stub re-recording job** (introduced in ADR-0004) to ensure the smoke load test stub continues to match real-SLM contract outputs at the new SHA.

A model upgrade that also changes the prompt template requires a coordinated prompt-template version bump per Principle XVI and a separate ADR for the prompt change.

#### Rollback procedure (reverse)

A rollback is triggered by:

- An SLO breach in CI or production attributable to the new SHA, OR
- An eval-suite regression detected on a scheduled `workflow_dispatch` run, OR
- A discovered supply-chain or licensing event affecting the new SHA.

Rollback steps:

1. **Open a rollback ADR** (e.g., `0007-rollback-slm-to-adr-0002.md`) that supersedes the upgrade ADR and reinstates this ADR's pin. The rollback ADR cites the trigger (SLO breach, eval drop, supply-chain alert) and links the relevant CI run or incident.
2. **Revert the configuration**: a single PR reverts the model SHA, the runtime version, the image digest, the GGUF artifact, and the SBOM to the values fixed by this ADR.
3. **Redeploy**: roll the SLM container forward (semantically backward) using the cached weights from step 7 of the upgrade procedure. No external network fetch should be required during rollback.
4. **Re-run the contract test** against the restored SHA to confirm parity with this ADR's baseline.
5. **File a postmortem** under `docs/postmortems/` describing the trigger, the timeline, and the prevention plan. The rollback ADR links to the postmortem.
6. **Update audit records going forward**: audit records produced after rollback carry the restored `slm.revision`. Audit records produced under the failed upgrade remain immutable and continue to point at the failed SHA, preserving the historical truth.

A rollback that exceeds the 90-day cached-weights window requires a fresh build from the upstream Hugging Face revision and a checksum re-verification against `config/slm/qwen2.5-7b-instruct/manifest.sha256`.

## Consequences

### Positive

- Apache 2.0 license is unambiguous for redistribution, embedding in containers, and SBOM disclosure; no MIT-vs-Apache-attribution edge cases.
- `qwen2` is mainline in vLLM with first-class support, removing the `trust_remote_code` exception a `phi3` choice would have required and lowering the supply-chain trust surface.
- 7B parameters give materially better structured-output reliability than a 3.8B alternative on multi-field schemas like `CollectionPolicySpec`, where field interactions matter (e.g., signal name choice influencing sampling-rate choice).
- Established constrained-decoding patterns: outlines and instructor both publish working examples against `qwen2`-family models, lowering the integration risk for ADR-0003.
- Long-form Apache 2.0 alignment with Sonatus's downstream OEM redistribution posture (no special-case licensing call-outs in customer documentation).

### Negative

- 7B at bf16 requires roughly 14 GB of GPU memory for weights alone, plus KV cache. The GPU instance choice in ADR-0005 must accommodate this; an `Nvidia A10G` (24 GB) is the smallest comfortable footprint, ruling out `g5.xlarge` for production-equivalent throughput. `g5.2xlarge` is the practical floor; `g6` is the forward-looking equivalent.
- Throughput on a single GPU at the Principle XI p95 budget (12 seconds end-to-end, with the SLM consuming a portion of that) constrains batch-decoding strategy. Mitigation lives in the plan: bounded backpressure, request-queue tuning, vLLM batch settings.
- Last upstream modification is 2025-01-12, older than Phi-4-mini-instruct's 2025-12-10. Older upstream means fewer post-training improvements; mitigated by the eval-suite gate, which measures actual quality rather than recency.
- CPU fallback (Q4_K_M GGUF on llama.cpp) is materially slower and not SLO-conformant; it exists for the local quickstart, not for production reads. This is recorded explicitly so a future contributor does not mistake the CPU profile for a deployment option.

### Neutral

- The `PolicyGeneratorClient` interface is identical for the GPU and CPU profiles; swapping is a Compose profile flag, not a code change.
- The future opt-in LLM upgrade path mandated by Principle XIII is not affected by this decision; the LLM client stub remains in the interface and remains opt-in via configuration.
- A future minor-version refresh (e.g., a hypothetical Qwen2.5-7B-Instruct revision update on `main`) follows the upgrade procedure above; there is no implicit "follow main" mode.

## Alternatives considered

### Microsoft Phi-4-mini-instruct (`microsoft/Phi-4-mini-instruct` @ `cfbefacb99257ffa30c83adab238a50856ac3083`, MIT)

Rejected as the default. Reasons:

- Smaller (~3.8B) than Qwen2.5-7B; structured-output reliability on multi-field schemas under constrained decoding is materially harder to keep at the 100% schema-completeness target Principle XIV pins.
- `phi3` architecture in vLLM requires `trust_remote_code=True`, which adds a non-trivial supply-chain consideration: arbitrary Python in the model repository is loaded at import time. Principle IX's supply-chain stance is workable here, but Qwen2.5 avoids the exception entirely.
- MIT license is permissive but adds an attribution edge case to the SBOM and to OEM-facing redistribution that Apache 2.0 sidesteps.
- More recent upstream tuning (2025-12-10) is the one strong argument for Phi-4; not strong enough to overcome the structured-output and architecture-mainline considerations.

Phi-4-mini-instruct remains a candidate for the CPU-only quickstart profile in environments where the 7B GGUF Q4_K_M is too slow to be useful, but that variant would be a distinct ADR (and is deferred).

### Larger Qwen variant (e.g., `Qwen/Qwen2.5-14B-Instruct`)

Rejected. The quality gain is real but the GPU memory footprint roughly doubles, pushing the AWS instance choice in ADR-0005 to `g6.4xlarge`-class hardware, which is incompatible with the bounded CI cost discipline encoded in Principles VII and XIV. Re-evaluate if the 7B baseline fails the eval gate; the upgrade procedure above is the correct vehicle.

### Quantized Qwen2.5-7B (`AWQ`, `GPTQ`, or `bf16 → fp8`)

Rejected at default. AWQ/GPTQ improves throughput at the cost of marginal quality regression that is hard to quantify on a structured-output task; fp8 requires hardware support not present on the default `g5`/`g6` SKUs at writing. The eval gate baseline runs on bf16 first; quantization is a future ADR if the bf16 baseline fails Principle XI's latency budget.

### Frontier LLM (any cloud-hosted model from any provider)

Rejected per Principle XIII, which forbids any frontier-LLM SaaS dependency in feature 001 and mandates an opt-in upgrade path with a constitution-amendment ADR before activation. Not in scope for this ADR.

## References

- Hugging Face model card: <https://huggingface.co/Qwen/Qwen2.5-7B-Instruct>
- Hugging Face Hub API revision pin: <https://huggingface.co/api/models/Qwen/Qwen2.5-7B-Instruct/refs>
- Qwen2.5 technical report (arXiv:2407.10671) and base model: <https://huggingface.co/Qwen/Qwen2.5-7B>
- vLLM v0.20.1 release: <https://github.com/vllm-project/vllm/releases/tag/v0.20.1>
- llama.cpp release `b9090`: <https://github.com/ggml-org/llama.cpp/releases/tag/b9090>
- Constitution Principle XIII (v1.0.1) at `.specify/memory/constitution.md`
- Constitution Principle XIV (deterministic CI) at `.specify/memory/constitution.md`
- ADR-0001 (COVESA VSS pin) — independent decision; both this ADR and ADR-0001 record their pin in the same audit record per Principle XVII
- ADR-0003 (constrained-decoding library) — drafted next; this ADR's decoding behavior depends on it
- ADR-0005 (SLM hosting topology on AWS) — drafted as part of `/speckit-plan`; the GPU SKU choice depends on this ADR's memory footprint
