# CollectMind Threat Model — Feature 001

**Owner**: Engineering, Security
**Last reviewed**: 2026-05-11
**Status**: Active for feature `001-policy-loop-vertical-slice`
**Scope**: Single-tenant; brake-wear hypothesis class; synthetic upstream + downstream simulators. Multi-tenant isolation is a separate feature.

Per Constitution Principle IX (NON-NEGOTIABLE) and research-note R-019 this document enumerates six threats — three named in `specs/001-policy-loop-vertical-slice/spec.md` Assumptions and three required by the constitutional posture (Principles IX, X, XIII). Each is mapped to the functional requirement(s) that defend it and to the test(s) that verify the defense.

The framing is STRIDE for the inbound surface and LINDDUN for the data-handling surface. Threats that span both surfaces are recorded under STRIDE.

## 1. Spoofed tenant claim (STRIDE: Spoofing)

**Threat**: An attacker who obtains a JWT signed by the configured OAuth2 issuer but minted for a different `client_id` could attempt to publish findings under another tenant's identity, contaminating the registry and the audit trail.

**Attack surface**: `POST /api/v1/findings`, `GET /api/v1/policies/*`, every authenticated endpoint.

**Defenses (FRs)**:
- **FR-002** rejects any inbound event without a valid JWT bearer token and any token whose `tenant_id` claim is missing or empty. The `tenant_id` populates the composite finding key; an attacker cannot forge the claim without compromising the issuer's signing key.
- **FR-018** requires authentication on every external endpoint except `/health` and `/ready`.

**Verifying tests**:
- `tests/contract/test_orchestration_api_contract.py` exercises the 401 path under schemathesis.
- `tests/unit/test_vss_validator.py` does NOT cover this threat; it covers the validator path. The orchestration contract test is the gate.

**Residual risk**: Compromise of the issuer's signing key bypasses this defense. Mitigation: JWKS rotation cadence is pinned in the runbook; expired keys are rejected by the cache (`jwt_verifier.py` 5-min TTL).

## 2. Replayed event (STRIDE: Repudiation / Information disclosure)

**Threat**: An attacker captures a valid signed event and replays it (a) past its `exp` to attempt to bypass the validity window, or (b) under a duplicated `finding_id` to flood the registry with redundant policy versions and the audit log with redundant rows.

**Attack surface**: `POST /api/v1/findings`.

**Defenses (FRs)**:
- **FR-002a** rejects any JWT whose `exp` claim is in the past with a structured error; the payload is NOT inspected. This forecloses (a).
- **FR-012** treats duplicate publications of `(tenant_id, finding_id)` as idempotent: a single policy version and a single deployment record are produced regardless of the number of replays. This forecloses (b).
- **FR-017a** audit-record minimum field set lets a reviewer trace the replay attempt through the audit trail.

**Verifying tests**:
- `tests/unit/test_idempotency_unit.py` and `tests/integration/test_idempotency_integration.py` cover (b).
- `tests/contract/test_orchestration_api_contract.py` covers the 401 expired-token path for (a).

**Residual risk**: Replay against a still-valid token within its `exp` window with a fresh `finding_id` is indistinguishable from legitimate traffic by design; rate limiting (deferred to feature 002) is the next defense.

## 3. Semantic abuse via schema-conformant payload (STRIDE: Tampering / Elevation of Privilege)

**Threat**: A payload that conforms structurally to the documented event schema but carries semantically invalid content (unsupported `schema_version` major; non-VSS signal names; out-of-bounds collection window) attempts to drive the policy engine into an undefined state.

**Attack surface**: `POST /api/v1/findings` payload body.

**Defenses (FRs)**:
- **FR-003a** rejects any inbound event whose `schema_version` declares an unsupported major version with a structured error.
- **FR-005 + FR-006** validate every signal name in the generated policy against the COVESA VSS v6.0 canonical vocabulary; non-VSS signals are rejected and named in the error response.
- **FR-009a** rejects any policy whose requested collection window exceeds 168 hours of logical time.
- **FR-017a** audit-record minimum field set carries the `inbound_schema_version` on every audit row so semantic-abuse attempts are traceable.

**Verifying tests**:
- `tests/unit/test_vss_validator.py` (property-based VSS coverage).
- `tests/integration/test_vss_rejection.py`.
- `tests/unit/test_schema_version.py`.

**Residual risk**: Semantically valid but operationally malicious findings (e.g., a finding whose hypothesis is technically correct but designed to exhaust GPU capacity) are out of scope here; the GPU node-group capacity runbook (`observability/runbooks/gpu-node-group-capacity-exhausted.md`) is the operational defense.

## 4. SLM supply-chain compromise (LINDDUN: Linkability / Non-repudiation; STRIDE: Tampering)

**Threat**: A weight file or a runtime image downloaded from the upstream registry has been tampered with after publication, or the published artifact itself is malicious. A compromised SLM could exfiltrate findings, produce schema-valid but security-hostile policies, or claim a different model identity in audit fields.

**Attack surface**: SLM container build (`infra/compose/gpu-profile/Dockerfile.vllm`) + runtime weight load.

**Defenses (FRs / Principles)**:
- **Constitution Principle IX**: model weights are treated as supply-chain artifacts. Each weight file's SHA-256 is recorded in `config/slm/qwen2.5-7b-instruct/manifest.sha256` and verified at container start. A digest mismatch fails the readiness probe closed.
- **ADR-0002** pins the model revision SHA, runtime version, quantization profile, and (as of Phase 5) the vLLM image manifest-list digest. The container's `entrypoint` passes the revision explicitly to vLLM.
- **FR-017a** records `slm_repo`, `slm_revision_sha`, `slm_runtime`, `slm_runtime_version`, `slm_quantization`, and `slm_decoding_seed` on every `generated` audit row so a compromised model claiming a different identity is detectable from the audit trail.
- **T126** CI guard (`scripts/check_slm_pinning.py`) asserts the digest pin in the Dockerfile and refuses any workflow that sets `SLM_PROFILE=dev_default`.
- **Syft SBOM** (T124) records the weight manifest alongside Python deps on every build.

**Verifying tests**:
- `tests/contract/test_slm_client_contract.py` runs against the real SLM container under deterministic decoding; a weight or runtime mismatch fails the contract.
- `scripts/check_slm_pinning.py` runs in CI on every PR.

**Residual risk**: A malicious upstream that publishes a weight identical in SHA-256 to a previous version but with hidden behavior would defeat checksumming. Mitigation: the upgrade path requires a fresh eval-suite run (per ADR-0002) before a new SHA is accepted.

## 5. Prompt injection from hypothesis text (LINDDUN: Identifiability)

**Threat**: The diagnostic finding's `hypothesis_statement` field is operator-supplied free text that flows into the SLM's prompt. A crafted hypothesis could attempt to override the system prompt, leak the system prompt into the output, or coerce the generator into emitting policies that target signals beyond the candidate set.

**Attack surface**: `hypothesis_statement` field on `DiagnosticFinding` → `prompts/policy_generator/v1.0.0/user.md`.

**Defenses (FRs / Principles)**:
- **Constitution Principle XIII**: structured output is schema-constrained at decode time via outlines (ADR-0003). A prompt-injection attempt cannot produce a non-CollectionPolicySpec output; the schema constraint is applied at every token, not as a post-hoc validation.
- **FR-005 + FR-006**: even if the generator is coerced into proposing a non-VSS signal, the validator rejects it.
- **FR-009a**: the window bound rejects oversize collection windows even if the SLM is coerced.
- **Constitution Principle XII**: the Policy Generator is the only node that talks to the SLM; the orchestrator and validator are deterministic Python. Injection cannot pivot to other nodes.
- The SLM container's egress is restricted to observability endpoints only (`infra/terraform/networking/main.tf` `aws_security_group.slm`), so even a fully-compromised generator cannot exfiltrate findings.

**Verifying tests**:
- `tests/contract/test_slm_client_contract.py` (schema-conformance under deterministic decoding).
- `tests/unit/test_models.py` (CollectionPolicySpec invariants).
- `tests/integration/test_vss_rejection.py` covers the "non-VSS signal slipped through" outcome.

**Residual risk**: A skilled injection that produces a schema-valid policy targeting weak-but-permissible signals is structurally indistinguishable from a legitimate policy. Detection relies on outcome-record statistics (`collectmind_policy_outcome_total` confirmation rate, `policy_retry_total` retry rate) plus periodic eval-suite runs.

## 6. Dashboard leakage (LINDDUN: Detectability; STRIDE: Information disclosure)

**Threat**: The operator dashboard renders metrics with high-cardinality labels (`tenant_id`, `route`, `runtime`). A bug in label sanitization or in the structured logging config could expose PII, secrets, or raw signal payloads in dashboard panels, traces, or metric labels.

**Attack surface**: `observability/grafana/dashboards/collectmind-end-to-end.json`, `src/collectmind/observability/logging.py`, `src/collectmind/observability/metrics.py`.

**Defenses (FRs / Principles)**:
- **FR-017** excludes personal data and raw signal payloads above a configured size from logs, traces, and metric labels.
- **SC-007** verifies the absence of PII in every log line, trace span, and metric label by an automated check on every build (T142 wires this in Phase 6 Polish).
- **Constitution Principle X** flags PII-adjacent signals in `config/vss/v6.0/pii_signals.yaml`; the validator rejects them without consent (`src/collectmind/validator/governance.py`).
- The dashboard JSON is contract-tested by T105 against the declared metric set: a new label cannot land in the dashboard without being declared in `metrics.py`, and labels are by construction kept low-cardinality (`tenant_id`, `state`, `runtime`, `digest`, `sha`, `route`, `status_class`, `reason`, `kind`).

**Verifying tests**:
- `tests/contract/test_dashboard_provisioning.py` enforces the declared-metric / referenced-metric parity.
- `tests/unit/test_pii_strip.py` (T142, Phase 6) verifies PII-stripping in structured logs.

**Residual risk**: Custom dashboards authored by operators (outside this repo) can violate FR-017 by adding labels the central dashboard does not. Mitigation: the central dashboard auto-provisions to Grafana on every Compose start; operator-added dashboards are out of scope and the runbook (`observability/runbooks/INDEX.md`) directs reviewers to the central one as the only source of truth.

## Coverage summary

| Threat | FRs that handle it | Tests that verify | Principles |
|---|---|---|---|
| 1. Spoofed tenant claim | FR-002, FR-018 | contract:orchestration-api 401 | IX |
| 2. Replayed event | FR-002a, FR-012, FR-017a | unit + integration idempotency; contract 401 expired | IX |
| 3. Semantic abuse | FR-003a, FR-005, FR-006, FR-009a, FR-017a | unit:vss, integration:vss_rejection, unit:schema_version | X |
| 4. SLM supply-chain | Principle IX, ADR-0002, FR-017a | contract:slm_client, scripts/check_slm_pinning.py | IX, XIII |
| 5. Prompt injection | Principle XIII (outlines), FR-005, FR-006, FR-009a, Principle XII | contract:slm_client, unit:models, integration:vss_rejection | XII, XIII |
| 6. Dashboard leakage | FR-017, SC-007 (T142), Principle X | contract:dashboard, unit:pii_strip (Phase 6) | V, X |

## Review cadence

This document is reviewed at every feature checkpoint. A new feature's plan MUST cite the threats from this document that apply to it, name any new threats the feature introduces, and either extend this document or supersede it via a new ADR. Per Constitution Principle XVIII reviewers explicitly verify the threat-to-FR mapping during the security spot-check.
