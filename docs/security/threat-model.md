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

## 7. Rate-limit bypass via JWT-issuer forgery (Feature 002; STRIDE: Spoofing / Elevation of Privilege)

**Threat**: An attacker mints a JWT that the tenant-issuer's JWKS does not validate but the orchestration-api accepts (e.g., via JWKS-cache poisoning, a forged `kid` matching a rotated key still cached, or a downgrade to a weaker signing algorithm). The forged token carries an arbitrary `tenant_id` claim. Once accepted, every downstream layer — RLS context, rate-limit counter, hot-store key shape, deployment-client scope check — derives tenant identity from the forged claim. The attacker either (a) impersonates a high-volume tenant to consume that tenant's rate-limit budget OR (b) impersonates a low-volume tenant whose limit is configured high to bypass the limiter entirely.

**Attack surface**: `src/collectmind/auth/jwt_verifier.py` (JWKS cache + algorithm whitelist), `src/collectmind/ratelimit/middleware.py` (the limiter inherits `principal.tenant_id` from the verifier), the operator-issuer's signing keypair at `infra/compose/operator-issuer/jwks.json`.

**Defenses (FRs / Principles)**:
- **FR-007** scopes tenant identity to the verified JWT `tenant_id` claim exclusively; body / header / path parameters cannot override.
- **FR-017** prevents rate-limit counter charges against unauthenticated requests — verification runs BEFORE the limiter so a forged-but-rejected token never advances any counter.
- **Constitution Principle IX**: JWKS pinned with a documented refresh cadence (`Settings.oauth2_jwks_cache_ttl_seconds`); algorithm whitelist enforced inside `JWTVerifier.verify`; `kid` mismatch raises `AuthInvalidToken` rather than falling back to an alternate key.
- **Operator issuer is distinct**: the operator-issuer JWKS is published at a different URL with a different audience claim (`collectmind-operator`); a forged tenant token cannot reach the break-glass surface even if the tenant-issuer is compromised.

**Verifying tests**:
- `tests/unit/test_operator_principal.py` exercises audience-discrimination.
- `tests/contract/test_negative_path_cross_tenant_admin.py` asserts a tenant JWT presented at the operator endpoint returns 401.
- `tests/integration/test_negative_path_e2e.py` walks the cross-tenant attack vectors end-to-end.

**Residual risk**: Compromise of the upstream OAuth2 issuer's signing key bypasses every defense at this layer. Mitigation is the issuer's own key-rotation runbook and the SBOM-driven supply-chain check (`scripts/check_secrets.py` + Trivy + Syft) catching unauthorized binaries that could be the compromise vector. Defense-in-depth: the deployment-client tenant-scope check (Threat 9) catches mismatched deployments even when the JWT layer is bypassed.

## 8. Break-glass abuse via operator-key compromise (Feature 002; STRIDE: Elevation of Privilege; LINDDUN: Identifiability)

**Threat**: An attacker obtains an operator credential (operator-issuer signing key, or a long-lived operator JWT) and uses the `POST /api/v1/audit/break-glass/query` primitive to read audit chains across multiple tenants. The primitive is privileged by design — it bypasses tenant-scoped RLS to satisfy regulator-driven cross-tenant retrieval. A burst of unauthorized invocations reads PII-adjacent audit content from tenants the operator is not authorized to administer.

**Attack surface**: `src/collectmind/audit_admin/api.py` (the break-glass router), `src/collectmind/auth/operator_principal.py` (operator-audience verification), the operator-issuer signing material in production AWS Secrets Manager (dev keypair at `infra/compose/operator-issuer/jwks.json` is clearly labeled non-production).

**Defenses (FRs / Principles)**:
- **FR-005a** scopes every invocation to a single named tenant scope; the bypass cannot widen mid-flight.
- **FR-005b atomic-audit**: every invocation writes an immutable `kind=break_glass` row carrying the operator subject + tenant scope + reason code + correlation id BEFORE the bypassed SELECT returns. Audit-row INSERT failure aborts the transaction; the SELECT result is never returned.
- **Phase 13 alerts**: `BreakGlassInvoked` (page on every invocation per (operator, reason) tuple) + `BreakGlassBurstInvocation` (critical on > 0.05/s for 5 min per operator). Single-event visibility means an unauthorized read pages within one scrape interval; burst detection means a credential-compromise spree is visible within minutes.
- **Constitution Principle XVII**: audit-row queryability is the operator-side accountability mechanism. The audit chain is the system of record for forensic review.
- **Reason-code enumeration** prevents free-form abuse: the documented enumeration (`incident_response`, `legal_hold`, `regulator_request`, `support_escalation`, `operator_self_audit`) means every invocation carries a reviewable justification.

**Verifying tests**:
- `tests/contract/test_audit_admin_break_glass_contract.py` asserts operator JWT → 200; tenant JWT → 401; missing reason_code → 400.
- `tests/integration/test_break_glass_atomic_audit.py` exercises the atomic-audit property (SC-013) against the real local stack.
- `tests/unit/test_audit_kinds.py` pins the per-kind minimum field set the writer enforces.

**Residual risk**: Compromise of the operator-issuer key + a window before the rotation is observed permits unauthorized invocations. The atomic audit row makes every invocation forensically reconstructible; the `BreakGlassBurstInvocation` alert escalates within 5 minutes. Mitigation requires the operator-issuer to rotate keys on a documented cadence and to support immediate revocation (out of scope for feature 002 — gated to a separate "operator-issuer hardening" feature). The runbook at `observability/runbooks/break-glass-burst-invocation.md` documents the credential-rotation response.

## 9. Tenant-vehicle ownership-data integrity attack (Feature 002; STRIDE: Tampering / Repudiation)

**Threat**: An attacker with write access to the `tenant_vehicles` table (e.g., via SQL injection on a service-principal-only operator endpoint, or via a compromised migration runner) transfers a vehicle's ownership row from its legitimate tenant to the attacker's tenant. The deployer-node tenant-scope check (FR-021) then accepts deployments from the attacker against the targeted vehicle because the ownership store now agrees.

**Attack surface**: `src/collectmind/registry/tenant_vehicles.py` (`TenantVehiclesRepository.assign`), the `tenant_vehicles` + `tenant_vehicles_history` schema (migration 015), `src/collectmind/cache/ownership_cache.py` (operator-level cache used by the deployer).

**Defenses (FRs / Principles)**:
- **ADR-0009 Part 3 atomic-audit**: every `INSERT` / `UPDATE` to `tenant_vehicles` fires the `tenant_vehicles_audit_trigger` writing a `kind=vehicle_assignment_change` audit row in the same transaction. A trigger-write failure aborts the assignment.
- **ADR-0009 Part 1 append-only history**: `tenant_vehicles_history` records every transition (prev_tenant_id, new_tenant_id, operator_subject, reason_code, transition_at, correlation_id) with an immutability trigger refusing UPDATE/DELETE. A tampering attempt that does not also append a history row is detectable; a tampering attempt that DOES append a history row leaves an immutable forensic trail.
- **ADR-0007 service-principal-only writes**: the `tenant_vehicles` table grants INSERT/UPDATE only to the `collectmind_service_principal` role. Tenant JWTs cannot reach this surface; only the documented operator workflow (out of scope for feature 002; gated by a separate feature) can issue the write.
- **Deployer-node Fatal class** (FR-022 / ADR-0009 Part 6): even when the ownership store IS tampered, the deployer's `validate_tenant_scope` raises a Fatal that audits + pages on every mismatch between the policy's declared tenant and the ownership store's current owner. A successful tampering attack must MATCH the policy's declared tenant — a stricter constraint than typical tampering scenarios.

**Verifying tests**:
- `tests/integration/test_break_glass_atomic_audit.py` (transitive — uses the same atomic-audit pattern).
- `tests/integration/test_deployment_tenant_scope.py` (T272) walks every US4 acceptance scenario including the mismatch path.
- `tests/unit/test_deployer_tenant_scope.py` (T285 sweep) pins the FR-021 first-gate + FR-022 no-retry + FR-023 minimum field set contracts.
- `tests/unit/test_audit_kinds.py` parametrizes the `vehicle_assignment_change` audit row's minimum field set.

**Residual risk**: A compromise of the service-principal role itself (e.g., the Postgres superuser credential leaked from AWS Secrets Manager) bypasses every application-layer defense. Mitigation requires the secrets-manager IAM policy + the operator-issuer trust chain to be independent (no single compromise affects both). The `tenant_vehicles_history` table provides post-incident forensic reconstruction even when the current-state row is tampered.

## Coverage summary

| Threat | FRs that handle it | Tests that verify | Principles |
|---|---|---|---|
| 1. Spoofed tenant claim | FR-002, FR-018 | contract:orchestration-api 401 | IX |
| 2. Replayed event | FR-002a, FR-012, FR-017a | unit + integration idempotency; contract 401 expired | IX |
| 3. Semantic abuse | FR-003a, FR-005, FR-006, FR-009a, FR-017a | unit:vss, integration:vss_rejection, unit:schema_version | X |
| 4. SLM supply-chain | Principle IX, ADR-0002, FR-017a | contract:slm_client, scripts/check_slm_pinning.py | IX, XIII |
| 5. Prompt injection | Principle XIII (outlines), FR-005, FR-006, FR-009a, Principle XII | contract:slm_client, unit:models, integration:vss_rejection | XII, XIII |
| 6. Dashboard leakage | FR-017, SC-007 (T290), Principle X | unit:check_log_pii_gate, contract:dashboard | V, X |
| 7. Rate-limit bypass (forged JWT) | FR-007, FR-017, Principle IX | unit:operator_principal, contract:negative_path_admin, integration:negative_path_e2e | IX |
| 8. Break-glass abuse | FR-005a, FR-005b, SC-013 | contract:break_glass, integration:break_glass_atomic_audit, alerts:BreakGlassInvoked + BreakGlassBurstInvocation | IX, XVII |
| 9. Ownership-data tampering | FR-021, FR-022, FR-023, ADR-0009 | unit:deployer_tenant_scope, integration:deployment_tenant_scope, audit-trigger | IX, X, XVII |

## Review cadence

This document is reviewed at every feature checkpoint. A new feature's plan MUST cite the threats from this document that apply to it, name any new threats the feature introduces, and either extend this document or supersede it via a new ADR. Per Constitution Principle XVIII reviewers explicitly verify the threat-to-FR mapping during the security spot-check.
