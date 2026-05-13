# ADR-0006: Dev-only `DevDefaultPolicyClient` for the foundation smoke path

- Status: Accepted
- Date: 2026-05-10
- Deciders: Arun Veligatla (project author)
- Constitutional principle: XIII (SLM-First, Isolated, Swappable Model Boundary), with binding consequences for XIV (Deterministic, Budgeted Model Execution in CI), VI (Reproducible Local Dev and Deployment), and VII (CI/CD Gates Merges)
- Supersedes: none. Amends the enumeration of `PolicyGeneratorClient` implementations established in ADR-0002 §"PolicyGeneratorClient interface" and the deterministic-substitute rule in ADR-0004.

## Context

ADR-0002 fixed three implementations of `PolicyGeneratorClient`: a vLLM client (default GPU profile), an llama.cpp client (CPU fallback profile), and an LLM client stub that fails fast with `not-implemented` unless explicitly enabled. ADR-0004 added a fourth implementation, `FingerprintStubClient`, that is a deterministic substitute used in load and soak tiers and contract-tested against the real SLM so it cannot drift.

The implementation phase of feature 001 surfaced a fifth case that none of the prior ADRs covered: the foundation smoke test (Spec SC-008's "quickstart on a clean machine in under 10 minutes") must exercise the full LangGraph end to end without bringing the 14 GB Qwen2.5-7B-Instruct SLM container up. The deterministic stub raises `MissingFingerprint` on any input not pre-recorded; the real clients require GPU access and a multi-gigabyte weight pull. Neither is acceptable for the foundation-quickstart path.

Concretely, with no `DevDefaultPolicyClient`:

- `docker compose up` on a fresh clone cannot complete the brake-wear finding-to-outcome loop. Every inbound finding generates a unique fingerprint that the stub cannot resolve.
- The integration test tier (`tests/integration/test_e2e_finding_to_outcome.py` etc.) becomes either skipped or red on every PR until the corpus is pre-recorded against the real SLM (workflow_dispatch corpus job, per ADR-0004) — which itself requires GPU access that not every contributor has.
- The portfolio-grade quickstart promise (SC-008, 10-minute clean-clone-to-running) breaks.

The pragmatic options are:

1. **Add a fourth `PolicyGeneratorClient` implementation** that is schema-valid by construction, parameterized by the inbound finding fields, and dev-only.
2. **Force every developer to bring the SLM container up** before running integration tests. Rejected: violates SC-008 and contradicts the foundation-smoke story in `specs/001-policy-loop-vertical-slice/quickstart.md`.
3. **Ship the foundation smoke as the deterministic-stub corpus only**, requiring every contributor to pre-record corpus entries before running any integration test. Rejected: turns the corpus into a recurring maintenance tax and contradicts ADR-0004's framing (the corpus is for load/soak, not for arbitrary integration scenarios).

This ADR records option 1 and bounds its blast radius.

## Decision

**Adopt `DevDefaultPolicyClient` as a fifth, dev-only implementation of `PolicyGeneratorClient`, gated by `SLM_PROFILE=dev_default`, refused by CI and production environments via a startup guard.**

### Implementation surface

`src/collectmind/slm/dev_default_client.py`. Implements the same `PolicyGeneratorClient` Protocol as `VLLMClient`, `LlamaCppClient`, `FingerprintStubClient`, and the LLM client stub. The graph and runner do not know which implementation they are talking to.

### Behavior

1. The client extracts the inbound finding's `tenant_id`, `finding_id`, `vehicle_scope`, `upstream_confidence`, and `candidate_signals` from the rendered prompt (regex over the template-substituted user message).
2. Returns a deterministic, schema-valid `CollectionPolicySpec` whose `signals` list is built from the finding's `candidate_signals` (one entry per signal at 1 Hz / priority 5), or from a hard-coded brake-wear default when the prompt carries no candidate signals.
3. Sets `originating_finding` to `{tenant_id, finding_id}` from the prompt, `policy_id` to `policy-{finding_id}`, `version` to `"1.0.0"`, `confidence_threshold` to `upstream_confidence - 0.1`, `collection_window_hours` to 72.
4. Reports `RuntimeInfo` with `slm_repo="dev/default"`, `slm_revision_sha="0" * 40`, `slm_runtime="stub"`, `slm_runtime_version="dev-default"`, `slm_quantization="none"`, `constrained_decoding_library="none"`. The synthetic SHA matches the convention ADR-0004 established for `FingerprintStubClient` so audit consumers can treat both as "non-real-SLM" rows with a single check.
5. **Does NOT enforce decode-time grammar.** The output is schema-valid by construction; there is no constrained decoder. This is the explicit deviation from Principle XIII's "structured output MUST be schema-constrained at decode time."

### Gating: where this client is allowed to run

`DevDefaultPolicyClient` is acceptable in exactly one environment:

- **Local development on the foundation smoke path**, with `SLM_PROFILE=dev_default` explicitly set (the Compose default for feature 001 quickstart).

It is forbidden in:

- **PR CI** (`.github/workflows/ci.yaml`). Use `SLM_PROFILE=stub` against `FingerprintStubClient` per ADR-0004.
- **`workflow_dispatch` CI** (full SLM load, soak, eval). Use `SLM_PROFILE=vllm` against the real model per ADR-0002.
- **Cloud-deployed environments** (any AWS workspace defined by `infra/terraform/`). Use `SLM_PROFILE=vllm` per ADR-0002 + ADR-0005.

### Guard

Two guards refuse `DevDefaultPolicyClient` outside the allowed environment. Both MUST land before this ADR is considered fully enforced:

1. **Application-level startup guard** (this ADR): `src/collectmind/app.py` refuses to start when `SLM_PROFILE=dev_default` AND `COLLECTMIND_ENV` is anything other than `local` (default). Production and CI containers set `COLLECTMIND_ENV` to `ci`, `staging`, or `prod`.
2. **CI pipeline guard** (planned T126, Phase 5): `scripts/check_slm_pinning.py` greps every workflow file and refuses any that sets `SLM_PROFILE=dev_default`. T126 is extended in Phase 5 to explicitly enumerate the allowed values per workflow.

### Audit-record convention

Every audit record produced under `DevDefaultPolicyClient` carries `slm_repo="dev/default"`, `slm_runtime="stub"`, and `slm_revision_sha="0" * 40`. Audit consumers MUST treat these values as "not produced by a real SLM" and MUST NOT mistake the synthetic SHA for a real revision. The convention is shared with `FingerprintStubClient` (per ADR-0004) so a single audit filter excludes both.

## Consequences

### Positive

- SC-008 holds: the foundation quickstart runs in under 10 minutes on a clean clone without GPU access.
- The integration test tier (`tests/integration/*`) is exercised on every PR against the dev_default profile, surfacing pipeline regressions that the deterministic-stub-with-corpus path would mask.
- The `PolicyGeneratorClient` Protocol gains a fourth implementation behind the same interface, reinforcing the swappability claim in Principle XIII rather than violating it.
- The audit-record convention (synthetic SHA + `slm_runtime="stub"`) lets a single filter exclude both `FingerprintStubClient` and `DevDefaultPolicyClient` outputs from production audit queries.

### Negative

- **Explicit deviation from Principle XIII's decode-time-grammar requirement.** This ADR is honest about the deviation rather than papering over it. The compensation is the strict gating: the deviation does not leak outside local foundation development.
- The application-level startup guard is a runtime-only check; if `COLLECTMIND_ENV` is misconfigured in a real environment, the client could run. Mitigation: T126's CI guard refuses pipelines that set `SLM_PROFILE=dev_default` regardless of `COLLECTMIND_ENV`.
- Adds a fourth client to the contract-test matrix. The PR-tier contract test in `tests/contract/test_slm_client_contract.py` currently exercises only the stub when the SLM container is not reachable; it should also exercise `DevDefaultPolicyClient` (a follow-up adjustment, tracked as a Phase 6 polish item).

### Neutral

- `DevDefaultPolicyClient` is structurally a templating client, not a model client. A future variant that wraps a small local model (e.g., a 1.5B model on CPU) under the same interface is a different ADR.
- The `slm_repo="dev/default"` value is a string literal; not a real Hugging Face repository. Audit consumers MUST handle it as a sentinel.

## Alternatives considered

### Force the SLM container up for the foundation smoke

Rejected. Violates SC-008's 10-minute quickstart promise and excludes contributors without GPU access. The portfolio-grade quickstart is a hiring-manager-facing artifact; gating it on GPU access undermines the project's premise.

### Pre-record the corpus exhaustively so the deterministic stub answers every fingerprint

Rejected. The corpus would need a fingerprint per unique inbound finding, which is unbounded (`finding_id` and `vehicle_scope` are caller-supplied). Maintaining such a corpus is impossible by definition.

### Loosen `FingerprintStubClient` to fall back to a templated default on miss

Rejected. ADR-0004 specifies that the stub MUST raise `MissingFingerprint` on miss to force corpus updates and prevent silent drift. Adding a fallback would erase that guarantee. The dev_default client is intentionally a separate class so the stub's strictness is preserved.

### Build a fifth contract that lets vLLM run on CPU in a tiny mode

Rejected. vLLM does not support CPU-only inference for a 7B model at usable throughput, and a "tiny mode" wraper would not exercise the real decoding path. The cost of building this exceeds the cost of a templating client.

## References

- Constitution Principle XIII (SLM-First) at `.specify/memory/constitution.md`
- Constitution Principle XIV (Deterministic, Budgeted Model Execution in CI) at `.specify/memory/constitution.md`
- ADR-0002 (default SLM, Qwen2.5-7B-Instruct) at `docs/adr/0002-default-slm-qwen2-5-7b-instruct.md`
- ADR-0003 (constrained-decoding library, outlines) at `docs/adr/0003-constrained-decoding-library.md`
- ADR-0004 (deterministic-fingerprint stub) at `docs/adr/0004-fingerprint-stub.md`
- ADR-0005 (SLM hosting topology on AWS) at `docs/adr/0005-slm-hosting-topology.md`
- Spec Assumptions cross-reference at `specs/001-policy-loop-vertical-slice/spec.md`
- Source: `src/collectmind/slm/dev_default_client.py`
- Startup guard: `src/collectmind/app.py` (refuses `dev_default` when `COLLECTMIND_ENV != "local"`)
- Planned CI guard: T126 amendment in Phase 5
