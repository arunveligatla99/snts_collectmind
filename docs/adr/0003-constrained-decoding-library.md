# ADR-0003: Constrained-decoding library — outlines

- Status: Accepted
- Date: 2026-05-09
- Deciders: Arun Veligatla (project author)
- Constitutional principle: XIII (SLM-First, Isolated, Swappable Model Boundary), with binding consequences for XIV (Deterministic, Budgeted Model Execution in CI), XII (Agent Boundaries), and XVI (Contracts Are Machine-Readable and Versioned)

## Context

Constitutional Principle XIII mandates that "structured output MUST be schema-constrained at decode time, not validated after the fact" and that "decoding MUST use outlines, instructor, or an equivalent grammar-constrained decoder bound to the CollectionPolicySpec Pydantic v2 schema. A free-text response from the Policy Generator MUST be treated as a runtime fault, not a parse failure, and MUST route to the dead-letter queue."

That language partitions the candidate space into two architectural classes:

1. **Decode-time grammar enforcement.** The decoder masks logits during generation so only schema-compliant tokens can be emitted. Output is schema-valid by construction. Examples: `outlines`, `xgrammar`, `lm-format-enforcer`.
2. **Post-hoc validation with retry.** The model generates freely; the framework parses and validates against a Pydantic schema; on failure it retries with corrective context. Output is schema-valid only after `N` attempts. Example: `instructor`.

Class 2 violates Principle XIII directly: it is "validated after the fact," and a non-conformant generation is treated as a parse error, not a runtime fault. Class 1 is the only architecturally compliant family. ADR-0002 fixes the model (Qwen2.5-7B-Instruct on vLLM and llama.cpp). ADR-0003 fixes the constrained-decoding library that enforces the schema at the logit-mask layer.

The plan in `Section 5` and the `PolicyGeneratorClient` interface require that the same library, configured identically, run on both the GPU profile (vLLM) and the CPU fallback profile (llama.cpp). The library MUST integrate with both runtimes.

vLLM's `guided_decoding_backend` configuration option accepts multiple backends. As of vLLM v0.20.1, the runtime default is `xgrammar`, with `outlines` and `lm-format-enforcer` as supported alternatives. The choice in this ADR is therefore not just "which library" but also "which backend does the SLM container request from vLLM," and how the same schema is enforced under llama.cpp on the CPU profile.

## Decision

**Default constrained-decoding library: `outlines`.**

| Field | Value |
|---|---|
| PyPI package | `outlines` |
| Pinned version | `1.2.13` |
| License | Apache-2.0 |
| Source URL | <https://pypi.org/project/outlines/1.2.13/> |
| Project home | <https://github.com/dottxt-ai/outlines> |
| Class | Decode-time grammar enforcement (logits-mask FSM) |
| Pydantic integration | First-class. `outlines.from_pydantic(CollectionPolicySpec)` produces a generator bound to the v2 model. |

### Runtime integration

| Profile | Runtime | Wiring |
|---|---|---|
| GPU (production-equivalent) | vLLM v0.20.1 (per ADR-0002) | The SLM container starts vLLM with `--guided-decoding-backend outlines`. The `PolicyGeneratorClient` HTTP body sets `extra_body={"guided_json": CollectionPolicySpec.model_json_schema()}` on every generation call. |
| CPU fallback | llama.cpp `b9090` (per ADR-0002) | The CPU adapter uses the `outlines.models.llamacpp` integration to bind the same Pydantic schema to a llama.cpp `Llama` instance loaded from the GGUF artifact. The same `CollectionPolicySpec` model is passed in both profiles, so the schema-enforcement boundary is identical. |

### Behavior contract

1. Every Policy Generator call passes the JSON schema derived from `CollectionPolicySpec.model_json_schema()` into the constrained decoder. The schema version is recorded in audit records as `slm.schema_version`.
2. The decoder MUST emit a token sequence that parses cleanly into a `CollectionPolicySpec` instance under Pydantic v2's `model_validate_json`. Any deviation is a runtime fault.
3. Constraint enforcement happens at decode time. Post-hoc validation is added as a defense-in-depth check (`CollectionPolicySpec.model_validate_json` on the raw output), and any post-hoc failure increments `slm_constraint_violation_count` and routes the session to the dead-letter queue per Principle XII. Under correct operation that counter MUST stay at zero.
4. Decoding parameters from ADR-0002 (`temperature=0`, `top_p=1.0`, `top_k=-1`, fixed seed) apply unchanged. The constrained decoder operates on top of the same sampling configuration.
5. The library version is pinned in `pyproject.toml` and `uv.lock` (or `poetry.lock`); upgrades require a superseding ADR.

### CI behavior (Principle XIV)

- Contract tests for `PolicyGeneratorClient` exercise both profiles (vLLM + outlines, llama.cpp + outlines) against a fixed input fingerprint and assert byte-identical output. Drift between profiles fails the test.
- The deterministic-fingerprint stub introduced in ADR-0004 is contract-tested against the real outlines-driven SLM, so the stub cannot drift away from real behavior.
- The contract-test budget remains 60 seconds per run per profile (per the constitution's Testing Standards). outlines compiles the schema FSM once per process and caches it; first-call compilation latency is amortized.

### Failure-mode mapping

| Failure | Class (Principle XIII) | Routing |
|---|---|---|
| Decoder cannot fit any token under the mask (model exhausts vocabulary candidates) | Runtime fault | Dead-letter queue, page on-call |
| Post-hoc Pydantic validation fails despite decode-time enforcement | Runtime fault (defense-in-depth tripped) | Dead-letter queue, page on-call, raise constraint-violation incident |
| Schema FSM compilation fails at SLM container start | Readiness probe fails closed | Container does not enter rotation |
| Schema version drift between client and server | Contract violation | Reject request with structured error before invoking the decoder |

## Consequences

### Positive

- Architectural compliance with Principle XIII is demonstrable: schema is enforced at the logit-mask layer, not via post-hoc retry.
- Pydantic v2 ergonomics are first-class. `CollectionPolicySpec` is the single source of truth for the schema across the orchestration API, the contract test, the Policy Generator, and the audit record. No hand-maintained JSON Schema duplication.
- Apache 2.0 license aligns with ADR-0002 (Qwen2.5-7B-Instruct, also Apache 2.0). SBOM disclosure is uniform; no MIT-vs-Apache dual-attribution edge cases.
- The library is named explicitly in Principle XIII; the choice does not require an "equivalent" justification, removing one degree of freedom for future drift.
- Both runtimes (vLLM, llama.cpp) have first-party outlines integration; the GPU/CPU swap is configuration, not code.
- The library is mature and widely used in production-grade structured-output systems; the supporting eval and tooling ecosystem (Pydantic AI, evaluation harnesses) treats it as a default.

### Negative

- vLLM's runtime default backend at v0.20.1 is `xgrammar`. Selecting `outlines` overrides the default. The override is recorded in `infra/compose/docker-compose.yaml` and the SLM container's Dockerfile entrypoint; it is a deliberate configuration, not an accident, and the rationale lives here. xgrammar may be measurably faster on some workloads.
- outlines compiles a finite-state automaton from the JSON schema at first use. The compilation happens once per process and is cached, but it adds a small startup cost to the SLM container's first request. Mitigation: warm the FSM during readiness-probe handling so it is ready before the container enters rotation.
- The library has had a non-trivial pace of breaking changes across major versions historically. The v1.x line is the stabilized API; pinning to `1.2.13` and gating upgrades by ADR is the explicit response.
- Contract-test parity between vLLM-outlines and llama.cpp-outlines is not byte-identical for arbitrary schemas in all cases (tokenization differences, sampling-implementation differences). The constitution's Testing Standards demand byte-identical output for the contract test; if a divergence is observed in practice, the contract test will fail and force either a runtime or a tokenizer-configuration alignment, not a relaxation of the constitution.

### Neutral

- The `instructor` library, despite being named in Principle XIII as a candidate, is not adopted. The constitution's "or an equivalent grammar-constrained decoder" clause is the explicit escape hatch for that nomination, and instructor's retry-based class is architecturally incompatible with the rest of the same principle. This ADR closes the apparent tension by eliminating one of the named candidates with reasoning.
- The `xgrammar` library is not adopted as the default but remains a credible alternative if outlines fails the eval-suite latency budget. A superseding ADR (`docs: ADR-NNNN switch decoder backend to xgrammar`) is the correct vehicle if that becomes necessary.
- A future move to `vLLM`'s native structured-outputs API (without explicit backend selection) would not change the architectural class; it would still be decode-time grammar enforcement. Such a move would be a superseding ADR.

## Alternatives considered

### `xgrammar` 0.2.0 (Apache 2.0, vLLM default backend)

Rejected as the default, but kept as a first-class alternative.

- Same architectural class as outlines (decode-time grammar enforcement), so principle compliance is not at issue.
- vLLM's default backend in v0.20.1; selecting xgrammar matches the runtime's own default and is likely faster on schema-heavy workloads.
- Pydantic ergonomics are slightly worse than outlines: xgrammar consumes a JSON Schema directly, so the project would generate `CollectionPolicySpec.model_json_schema()` on every call rather than passing the Pydantic class. This is a minor ergonomics gap, not a correctness issue.
- The CPU profile (llama.cpp) does not have first-party xgrammar integration as outlines does; bridging xgrammar to llama.cpp would require more glue code or a separate constrained-decoding stack on the CPU profile, breaking the "same library both profiles" property that this ADR values.
- If outlines fails the Principle XI latency budget under load testing, switching the default backend to xgrammar on the GPU profile (with outlines retained on the CPU fallback) is the correct mitigation; that is a future ADR, not a today decision.

### `instructor` 1.15.1 (MIT)

Rejected on architectural grounds.

- Class 2 (post-hoc validation with retry). The model generates freely; instructor parses, validates, and retries on failure with corrective context.
- Principle XIII is unambiguous: "schema-constrained at decode time, not validated after the fact" and "a free-text response from the Policy Generator MUST be treated as a runtime fault, not a parse failure." instructor inverts both halves.
- The library is also positioned around OpenAI-compatible chat APIs and tool/function calling; it does not bind to vLLM's logits-processor pipeline in the way the principle demands, and binding it to llama.cpp would be a similar mismatch.
- Naming instructor in Principle XIII reflects its prominence in the space, not its architectural fit. The "or an equivalent grammar-constrained decoder" clause is the explicit allowance to choose a different library that does meet the architectural class.

### `lm-format-enforcer` 0.11.3 (MIT)

Rejected.

- Same architectural class as outlines (decode-time grammar enforcement via logits-processor) so principle compliance is met.
- Slower than xgrammar and outlines on JSON Schema workloads in published benchmarks; no offsetting advantage for this project.
- MIT license; one-off dual-attribution case alongside the rest of the Apache-2.0 stack.
- No first-class Pydantic v2 integration story comparable to outlines'.

### Hand-rolled JSON-grammar enforcement on top of vLLM's `guided_json` with no library

Rejected.

- vLLM's `guided_json` parameter requires a backend; "no library" is not actually an option. Choosing it ships a backend by default (xgrammar in vLLM v0.20.1), which is just the xgrammar alternative above by another name.
- Owning the FSM-compilation code in this project is not a portfolio improvement; it is a maintenance burden and a regression in supply-chain hygiene (more code to vet).

### Defer the choice to plan time and let `/speckit-plan` pick

Rejected.

- The Policy Generator's contract is shaped by the decoder's behavior. Deferring this choice past ADR-0002 leaves the integration test for `PolicyGeneratorClient` undefined and forces a re-write of plan-time decisions. Locking the library now is the lower-cost path.

## References

- outlines on PyPI: <https://pypi.org/project/outlines/1.2.13/>
- outlines repository: <https://github.com/dottxt-ai/outlines>
- xgrammar on PyPI: <https://pypi.org/project/xgrammar/>
- xgrammar repository: <https://github.com/mlc-ai/xgrammar>
- instructor on PyPI: <https://pypi.org/project/instructor/>
- vLLM v0.20.1 release: <https://github.com/vllm-project/vllm/releases/tag/v0.20.1>
- vLLM guided decoding documentation (the runtime entrypoint that selects the backend): <https://docs.vllm.ai/en/latest/usage/structured_outputs.html>
- llama.cpp release `b9090`: <https://github.com/ggml-org/llama.cpp/releases/tag/b9090>
- Constitution Principle XIII (v1.0.1) at `.specify/memory/constitution.md`
- Constitution Principle XIV (deterministic CI) at `.specify/memory/constitution.md`
- ADR-0002 (default SLM, Qwen2.5-7B-Instruct) at `docs/adr/0002-default-slm-qwen2-5-7b-instruct.md`
- ADR-0004 (deterministic-fingerprint stub) — drafted as part of `/speckit-plan`; the stub is contract-tested against the outlines-driven `PolicyGeneratorClient` defined here
