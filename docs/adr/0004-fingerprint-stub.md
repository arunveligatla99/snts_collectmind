# ADR-0004: Deterministic-fingerprint Policy Generator stub

- Status: Accepted
- Date: 2026-05-09
- Deciders: Arun Veligatla (project author)
- Constitutional principle: XIV (Deterministic, Budgeted Model Execution in CI), with binding consequences for VII (CI/CD Gates Merges), II (No Mocked Subsystems Where a Real One Is Feasible), and XII (Agent Boundaries)

## Context

Constitutional Principle XIV is binding: contract and integration tests for the Policy Generator node MUST run against the real SLM under deterministic decoding, while smoke load, full-profile load, and 24-hour soak MUST NOT invoke the SLM and MUST instead use a deterministic substitute keyed by input fingerprint. The substitute is contract-tested against the real client so it cannot drift.

Principle VII forbids merges on red CI. Spec SC-009 caps the PR-tier pipeline at 20 minutes of cumulative time on average. A 7B-parameter SLM running on a CPU-profile container at PR time would breach that cap on its own, before any load is exercised; running it on a GPU runner for every PR breaches Principle VII's model-cost discipline. The substitute that Principle XIV demands is therefore not optional: without it, either Principle VII or Spec SC-009 fails.

Principle II forbids mocked subsystems where a real one is feasible. The substitute satisfies that principle only because it is contract-tested against the real SLM and is implementation-equivalent on the downstream path: every byte after the Policy Generator's output is real. The substitute's only job is to skip the part of the system that is too expensive to run at scale on every PR.

ADR-0002 fixes the model (Qwen2.5-7B-Instruct) and ADR-0003 fixes the constrained-decoding library (outlines). This ADR fixes the substitute that lets the rest of the system be exercised at scale without invoking either.

## Decision

**Define and adopt `FingerprintStubClient` as the third implementation of the `PolicyGeneratorClient` interface defined in `contracts/openapi/policy-generator-client.v1.yaml`.**

### Implementation surface

`FingerprintStubClient` lives at `src/collectmind/slm/stub_client.py`. It implements the same `PolicyGeneratorClient` interface as `VLLMClient` and `LlamaCppClient`. The deployer, validator, registry, and feedback worker do not know which implementation they are talking to.

### Fingerprinting algorithm

For each generation request, the stub computes a SHA-256 over a canonical-JSON serialization of the request fields that are semantically meaningful to the Policy Generator's behavior:

- `prompt_template_version`
- `decoding.temperature`
- `decoding.top_p`
- `decoding.top_k`
- `decoding.seed`
- The Pydantic-model JSON Schema in `schema`
- The fully rendered `prompt` text

It does **not** include the `session_id` (per-call identifier) or the JWT-derived principal subject; those are not part of the model's input space.

The hash is rendered as a 64-character hex string and used as a directory key under the corpus root.

### Golden corpus

`tests/fixtures/policy_corpus/` is the corpus root. Each fingerprint maps to a directory:

```
tests/fixtures/policy_corpus/
├── <hex_fingerprint_1>/
│   ├── input.json        # The full GenerationRequest used to record this entry
│   ├── output.json       # The CollectionPolicySpec the real SLM produced under deterministic decoding
│   ├── usage.json        # Token counts and generation latency from the recording run
│   └── metadata.json     # slm_repo, slm_revision_sha, runtime, runtime_version, prompt_template_version, recorded_at
└── ...
```

Recording is performed by a one-off CI job, `record-corpus.yaml`, gated to `workflow_dispatch`, that runs the real SLM against a curated input set and writes the fixture tree. The corpus is committed to the repository.

### Behavior

When the stub receives a `GenerationRequest`:

1. It computes the fingerprint per the algorithm above.
2. It resolves the corpus directory under that fingerprint and returns the recorded `output.json` as the `policy` field of the `GenerationResponse`, with `runtime_info.slm_runtime = "stub"`, `slm_quantization = "none"`, and `slm_revision_sha` set to a constant `"0"*40` so that audit records produced under the stub are unambiguously distinguishable from those produced by the real SLM.
3. If the corpus does not contain the fingerprint, the stub raises a typed `MissingFingerprint` error and the calling test fails. The CI guard prints the missing fingerprint and the input that produced it so the recorder job can be re-run.

The stub does not call the real SLM, the network, or the file system at any path outside the corpus. It is in-process and synchronous; latency is microseconds.

### Contract test against the real SLM (gate against drift)

`tests/contract/test_slm_client_contract.py` runs against **all** `PolicyGeneratorClient` implementations including `FingerprintStubClient`, asserting that for a fixed fingerprint:

- The Pydantic-validated `policy` is byte-equal across implementations under canonical JSON serialization.
- The schema-conformance check passes for every implementation.
- The constraint-violation counter is zero for every implementation.

Fixed fingerprint set:

- **PR tier**: one fingerprint, real SLM warmed via vLLM `/info` poll before the test starts; warm-path wall budget 60 seconds. Cold start is not measured (per R-020 update).
- **`workflow_dispatch` tier**: the full corpus, as a regression suite. No per-fingerprint budget; the suite has its own runbook entry.

If a real-SLM contract assertion regresses, the corpus is the source of truth: either the SLM has shifted (which violates Principle XIII's pinning, indicating a weight or runtime drift to fix) or the prompt template, schema, or decoding configuration has changed (which requires re-recording the corpus and a coordinated PR with both code and corpus changes).

### Where the stub is the active client

| Tier | Active client | Reason |
|---|---|---|
| Unit | `FingerprintStubClient` (default) or hand-built fakes per test | Fast, no SLM dependency |
| Contract | All three real implementations + the stub, in parallel | Stub-vs-real comparison is the contract |
| Integration | `VLLMClient` (GPU) or `LlamaCppClient` (CPU profile) on the real local stack | Principle XIV's "real model in integration" |
| Smoke load (PR tier) | `FingerprintStubClient` | Principle XIV's "deterministic substitute for load and soak" |
| Full-profile load (`workflow_dispatch`) | `VLLMClient` against the real GPU runner | SC-002 verification against the real model |
| 24-hour soak (nightly) | `VLLMClient` against the real GPU runner | SC-003 verification against the real model |

## Consequences

### Positive

- The PR-tier pipeline runs Locust at non-trivial concurrency without paying for a GPU runner on every PR; SC-009's 20-minute budget stays achievable.
- The stub keeps the application code path identical: the same `PolicyGeneratorClient` interface, the same FastAPI dependency injection, the same tracing and audit-record fields. Only the source of the policy bytes differs.
- The contract-test gate against the real SLM is the only place drift can be detected, and it runs on every PR, so drift is caught at the smallest unit of change.
- Running stub-vs-real byte comparisons in the contract tier turns the load suite's PR-tier signal into a real signal: if the load suite passes against the stub but the stub disagrees with the real SLM, the contract tier fails first.

### Negative

- The corpus must be regenerated whenever the prompt template version, the JSON schema, the decoding seed/parameters, or the model revision SHA changes. The recording job is gated to `workflow_dispatch` to make this a deliberate act, not an incidental one.
- Stub-vs-real byte equality requires the real SLM to produce stable bytes under the deterministic decoding configuration. If a future vLLM or outlines version introduces non-determinism (a known historical pain point), the contract test will fail and force a runtime upgrade ADR before merging.
- The corpus directory is checked in and grows with each fingerprint. Acceptable for a portfolio repository; would warrant a Git LFS or external-storage decision at production scale.

### Neutral

- The `slm_revision_sha = "0"*40` audit-record convention is an explicit "this row was produced by the stub" signal, not a missing value. Audit consumers MUST treat `slm_runtime == "stub"` as decisive and MUST NOT interpret the synthetic SHA as a real revision.
- A future `RecordingClient` (a real-SLM-backed wrapper that auto-records new fingerprints into the corpus during the recording job) is straightforward to add. It is intentionally not part of feature 001 scope.

## Alternatives considered

### Pure-mock stub with no contract test

Rejected. Principle II (no mocked subsystems where a real one is feasible) is satisfied here only because the stub is contract-tested against the real SLM. Drop the contract test and the stub becomes a mock; drift becomes inevitable; downstream tests stop signaling anything about correctness.

### Recording-and-replay against the real SLM each PR

Rejected. Wall-time and cost violation under SC-009 and Principle VII's model-cost discipline. Recording is a deliberate `workflow_dispatch` job, not a PR-time cost.

### Skipping load on PRs entirely

Rejected. SC-002 (sustained 1,000 events/s/tenant) and SC-003 (24-hour soak) would then run only on `workflow_dispatch`, with no PR-time signal that a code change is about to break the load profile. The stub is the cheapest signal that catches regressions in the downstream-of-SLM path on every PR.

### Property-based generation of synthetic policies (no real-SLM corpus)

Rejected. The stub then no longer represents what the real SLM actually does. The contract test becomes circular (the stub agrees with itself). The real-SLM agreement is the only thing that makes the substitute non-mock under Principle II.

## References

- Constitution Principle XIV (Deterministic, Budgeted Model Execution in CI) at `.specify/memory/constitution.md`
- Constitution Principle II (No Mocked Subsystems Where a Real One Is Feasible) at `.specify/memory/constitution.md`
- ADR-0002 (default SLM, Qwen2.5-7B-Instruct) at `docs/adr/0002-default-slm-qwen2-5-7b-instruct.md`
- ADR-0003 (constrained-decoding library, outlines) at `docs/adr/0003-constrained-decoding-library.md`
- Plan, research note R-016 (the inline draft this ADR supersedes) at `specs/001-policy-loop-vertical-slice/research.md`
- Contract: `specs/001-policy-loop-vertical-slice/contracts/openapi/policy-generator-client.v1.yaml`
