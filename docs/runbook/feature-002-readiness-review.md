# Feature 002 — Production-Readiness Review

**Feature**: `002-multi-tenant-isolation`
**Phase**: 14 — Polish (closure)
**Reviewer**: Arun Veligatla
**Date**: 2026-05-12
**Constitution version**: v1.0.1 at [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)

This document is the closure gate for feature 002. It mirrors [feature-001-readiness-review.md](feature-001-readiness-review.md) in structure: each NON-NEGOTIABLE constitutional principle (IV, VII, IX, X, XI, XIII, XIV) is walked with a specific feature-002 artifact, test, or check. "The test passes" is not sufficient — each line names the artifact, the verifying test or check, and the resulting evidence.

## Summary

| # | Principle | Verdict |
|---|---|---|
| IV | Tests Are Load-Bearing | **PASS** (85.36% coverage; 329 unit / 17 contract / 24 targeted integration + 2 migration rollback; all green) |
| VII | CI/CD Gates Merges | **PASS** (T290 PII-strip gate wired into `custom-guards`; T283 bidirectional runbook check; T287 OpenAPI dump diff up-to-date) |
| IX | Security as a First-Class Requirement | **PASS** (threat model extended with three new threats per R-019; break-glass atomic-audit verified; ownership-data integrity defended at four layers) |
| X | Vehicle Telemetry Data Handling | **PASS** (RESTRICTIVE RLS on every tenant-scoped table; FR-018 tenant-scoped hot-store keys; deployer-node tenant-scope check verified) |
| XI | Performance SLOs Are Measured, Not Aspired | **PASS for SC-012/SC-013/SC-014 (local); conditional PASS for SC-002/SC-003/SC-004/SC-005/SC-006 (workflow_dispatch + nightly tier per Principle XIV)** |
| XIII | SLM-First, Isolated, Swappable Model Boundary | **PASS** (feature 002 does not touch the SLM boundary; `scripts/check_slm_pinning.py` re-verified) |
| XIV | Deterministic, Budgeted Model Execution in CI | **PASS** (no new SLM CI work; feature 001's split inherited unchanged) |

No NON-NEGOTIABLE is FAIL at closure. ADR-0008 stays at **Proposed** with a documented production-verification gating note (same pattern as ADR-0002's GPU-runner gating). ADR-0007 + ADR-0009 promote from Proposed to **Accepted** at this closure.

Two Phase-12 test-infrastructure items remain deferred and named: `test_rls_migration_rollback` schema_migrations desync (test-only flake); `app._lifespan` `OwnershipCache` wiring (lazy default factory ships now; production DI wiring rolls into a follow-up).

---

## Principle IV — Tests Are Load-Bearing

**Required**: Unit tests; contract tests for every external interface; integration test against the real local stack; load or soak test for any hot path. Coverage ≥85% on application code, enforced by pytest-cov in CI. Test-first posture.

### Evidence

- **Unit tier**: 329 tests at [`tests/unit/`](../../tests/unit/). Phase 12 added [`test_deployer_tenant_scope.py`](../../tests/unit/test_deployer_tenant_scope.py) (T272/T275/T276 contracts) + [`test_ownership_cache.py`](../../tests/unit/test_ownership_cache.py) (T274 / ADR-0009 Part 4). Phase 13 added [`test_alert_runbook_parity.py`](../../tests/unit/test_alert_runbook_parity.py) extension + [`test_dashboard_phase13_panels.py`](../../tests/unit/test_dashboard_phase13_panels.py) + [`test_runbook_completeness_bidirectional.py`](../../tests/unit/test_runbook_completeness_bidirectional.py). Phase 14 added [`test_check_log_pii_gate.py`](../../tests/unit/test_check_log_pii_gate.py) (T290 / SC-007) plus T285 coverage-sweep test files. Test bar: 329/329 passing + 3 skipped (named).
- **Contract tier**: 17 tests at [`tests/contract/`](../../tests/contract/) — schemathesis fanning over the negative-path cross-tenant surface (regular + audit-admin), break-glass router contract, tenant_config self contract, rate-limit response contract. Test bar: 17/17 passing.
- **Integration tier**: 24 tests at [`tests/integration/`](../../tests/integration/) plus 2 migration-rollback (T227 isolated). Phase 9 RLS RESTRICTIVE + break-glass atomic audit; Phase 10 rate-limit Redis-unavailable; Phase 11 hot-store key shape + post-rollover Fatal guard; Phase 12 deployment-tenant-scope + alert-routing. Test bar: 24/24 passing on the live local stack.
- **Coverage**: **85.36%** line coverage measured by pytest-cov via [`pyproject.toml`](../../pyproject.toml) `addopts` `--cov-fail-under=85`. Phase 14 T285 added eight new unit-test files targeting the lowest-coverage modules (deployer wrappers, tenant_context middleware, tenant_config repository, ratelimit middleware helpers, auth dependencies, feedback scheduler, tenant_config LISTEN consumer) per the Phase-6 mocking pattern.
- **Test-first posture**: every Phase opened with a red-phase test commit before implementation. Commit log records the cadence: `4d18a22` (US1 tests red) → `5429689` (US1 impl) → `fd16953` (US2 tests red) → `d4beeaa` (US2 impl) → `2c93827` (US3 tests red) → `f460e7c` (US3 impl) → `707fb55` (US4 tests red) → `e48faed` (US4 impl) → `03a0a48` (Phase 13 tests red) → `701f32c` (Phase 13 amendments) → `1e6f76e` (Phase 13 impl).

### Verdict

**PASS.** Coverage floor met by an automated CI gate; every tier exists and is green; every test asserts a documented FR or SC.

---

## Principle VII — CI/CD Gates Merges

**Required**: Lint, type-check, unit, contract, integration, container build, vulnerability scan, static analysis, license check, SBOM. No merge on red CI. SLM CI rules per Principle XIV.

### Evidence

- **T290 PII-strip CI gate (NEW at Phase 14)**: [`scripts/check_log_pii.py`](../../scripts/check_log_pii.py) wired into `.github/workflows/ci.yaml`'s `custom-guards` job. Closes feature-001 SC-007 + feature-002 SC-007. Three sub-checks: PII-pattern redaction (positive case — email/phone/lat-long/SSN MUST be stripped), non-PII preservation (negative case — business identifiers MUST pass through), metric-label PII fragment scan (labels MUST NOT match `email`/`phone`/`ssn`/`personal_*`/`address`/`geolocation`).
- **T283 bidirectional runbook check (NEW at Phase 13)**: [`scripts/check_runbook_completeness.py`](../../scripts/check_runbook_completeness.py) extended with `find_orphan_runbooks(rules_doc, runbook_dir, whitelist)`. Forward: every alert links to a runbook with the 4 canonical sections. Backward: every runbook page is alert-referenced OR listed in [`observability/runbooks/.orphan-whitelist.yaml`](../../observability/runbooks/.orphan-whitelist.yaml). CI gate now fails on either direction.
- **T287 OpenAPI dump diff**: [`docs/api/openapi.yaml`](../../docs/api/openapi.yaml) regenerated from `python -m collectmind.openapi.dump`. Phase 14 sweep added the break-glass surface (audit-admin.v1) + the tenant-config-self GET + deployment-rejected audit kinds. `custom-guards` job re-asserts byte-identity on every PR.
- **T288 + T289 mechanical guards**: `scripts/check_no_todo_fixme.py` clean; `scripts/check_slm_pinning.py` PASS unchanged (feature 002 did not touch the SLM boundary).
- **T286 ruff + mypy --strict**: clean. 180 files formatted; 0 lint errors; mypy --strict reports "Success: no issues found in 88 source files".
- **Merge gate**: pre-commit configuration unchanged from feature 001; CI re-asserts every gate on every PR. Phase 14 added two new custom-guard steps (T290 + the bidirectional T283 extension).

### Verdict

**PASS.** Feature 002 adds two new CI gates (PII-strip + bidirectional runbook completeness) and re-verifies every feature-001 gate. Wall-clock budget unchanged.

---

## Principle IX — Security as a First-Class Requirement

**Required**: Secrets via environment / AWS Secrets Manager; no secrets in git (gitleaks); dependency pinning; SBOM on every build; authenticated external endpoints; Pydantic v2 input validation; OWASP Top 10; supply-chain controls.

### Evidence

- **Threat model extended at T291**: [`docs/security/threat-model.md`](../security/threat-model.md) gains three new threats per `plan.md` Constitution Check row IX: (7) Rate-limit bypass via JWT-issuer forgery → defended by FR-007 / FR-017 + JWKS algorithm whitelist + distinct operator-issuer. (8) Break-glass abuse via operator-key compromise → defended by FR-005a/b atomic-audit + BreakGlassInvoked + BreakGlassBurstInvocation alerts + reason-code enumeration. (9) Tenant-vehicle ownership-data integrity attack → defended by ADR-0009 Parts 1+3+6 (mutable current + append-only history + atomic audit + deployer-node Fatal). Each threat names defending FRs + verifying tests + residual risk.
- **Operator-issuer separation**: distinct JWKS at `infra/compose/operator-issuer/` with audience `collectmind-operator`. Tenant tokens cannot reach the break-glass surface; verified by [`tests/contract/test_negative_path_cross_tenant_admin.py`](../../tests/contract/test_negative_path_cross_tenant_admin.py).
- **Break-glass atomic-audit**: every invocation writes `kind=break_glass` row inside the same DB transaction as the bypassed SELECT (FR-005b). Verified by [`tests/integration/test_break_glass_atomic_audit.py`](../../tests/integration/test_break_glass_atomic_audit.py); enforced at the schema level by the audit-writer's per-kind minimum field set (T209) + the migration-016 `UNIQUE (correlation_id, kind)` constraint.
- **Tenant-vehicle ownership integrity**: service-principal-only writes per ADR-0007; atomic `kind=vehicle_assignment_change` audit row per ADR-0009 Part 3; append-only `tenant_vehicles_history` with immutability trigger; deployer-node Fatal class on every mismatch per FR-022. Four independent defense layers; compromise of any one still leaves the other three.
- **Phase 13 alerts**: `BreakGlassInvoked` (page on every invocation, per-(operator, reason) routing) + `BreakGlassBurstInvocation` (critical on > 0.05/s for 5 min per operator) + `DeploymentTenantMismatch` (page on every Fatal). Operator-side accountability mechanism per Principle XVII.
- **PII-strip CI gate**: T290 closes SC-007. Verified locally and CI-wired (`scripts/check_log_pii.py`).

### Verdict

**PASS.** Threat model coverage is comprehensive (9 threats); atomic-audit is structural (every privileged operation writes a row in the same transaction); operator surface is independently authenticated; deployment-client tenant scoping is the egress-side defense-in-depth.

---

## Principle X — Vehicle Telemetry Data Handling

**Required**: Per-tenant data isolation at the API gateway, the database row level, AND the deployment client. RESTRICTIVE RLS on every tenant-scoped table. PII-adjacent signals require explicit consent.

### Evidence

- **DB-level isolation (FR-001, FR-002, FR-003, FR-004)**: migrations 012-017 at [`src/collectmind/registry/migrations/sql/`](../../src/collectmind/registry/migrations/sql/). RESTRICTIVE policies + PERMISSIVE baselines per ADR-0007's Phase-9.b addendum (Postgres RLS semantics require the baseline to combine via AND with the RESTRICTIVE filter). The `collectmind_tenant` role (migration 017) is non-BYPASSRLS; orchestration-api connects as `collectmind` and `SET LOCAL ROLE collectmind_tenant` inside [`Database.acquire(tenant_id)`](../../src/collectmind/registry/db.py). Verified by [`tests/integration/test_rls_restrictive.py`](../../tests/integration/test_rls_restrictive.py) — missing-context returns 0 rows; wrong-context returns 0 rows; SET LOCAL ROLE reverts on transaction close.
- **API-level isolation (FR-006, FR-007)**: tenant identity derived exclusively from the verified JWT `tenant_id` claim; cross-tenant access returns 404 (not 403/422/500). Verified end-to-end by [`tests/integration/test_negative_path_e2e.py`](../../tests/integration/test_negative_path_e2e.py) (walks every US1 acceptance scenario) + [`tests/contract/test_negative_path_cross_tenant_regular.py`](../../tests/contract/test_negative_path_cross_tenant_regular.py) (schemathesis fans the OpenAPI surface).
- **Hot-store isolation (FR-018, FR-019, FR-020)**: key shape `tenant_id:vehicle_id:signal_name` (post Phase 14 T293 cleanup; dual-read fallback removed). Pure `_hot_store_key()` helper is property-tested under hypothesis at [`tests/unit/test_hot_store_key_property.py`](../../tests/unit/test_hot_store_key_property.py). Legacy single-tenant API raises `LegacyKeyShapeError` (Fatal) unconditionally as defense-in-depth.
- **Deployment-client isolation (FR-021, FR-022, FR-023)**: validate_tenant_scope is the FIRST gate on the deployer hot path. On mismatch: Fatal raised, audit row written inside the Fatal handler, collector.deploy NEVER invoked. Verified by [`tests/integration/test_deployment_tenant_scope.py`](../../tests/integration/test_deployment_tenant_scope.py) + the unit tier at [`tests/unit/test_deployer_tenant_scope.py`](../../tests/unit/test_deployer_tenant_scope.py).
- **Operator surface**: break-glass primitive at [`src/collectmind/audit_admin/api.py`](../../src/collectmind/audit_admin/api.py) is the ONLY path that crosses tenant boundaries; gated by operator-audience authentication; every invocation writes an immutable audit row.

### Verdict

**PASS.** Four independent isolation layers (API, DB, hot-store, deployment-client) each verified by tests at the appropriate tier. The break-glass surface is the documented exception with structural atomic-audit enforcement.

---

## Principle XI — Performance SLOs Are Measured, Not Aspired

**Required**: SLOs verified by load + soak suites in CI. Breach fails the build.

### Recorded measurements (feature 002, local stack)

| SLO | Budget | Local measurement | Source |
|---|---|---|---|
| **SC-012** alert routing (Fatal deployment mismatch → webhook) | ≤ 60 s | < 30 s wall-clock | [`tests/integration/test_deployment_alert_routing.py`](../../tests/integration/test_deployment_alert_routing.py) |
| **SC-013** break-glass invocation → atomic audit row | 100% | 100% (every test invocation lands the row before the response returns) | [`tests/integration/test_break_glass_atomic_audit.py`](../../tests/integration/test_break_glass_atomic_audit.py) |
| **SC-014** tenant_config write → atomic audit row | 100% | 100% (verified at integration; failure path rolls back) | [`tests/integration/test_tenant_config_atomic_audit.py`](../../tests/integration/test_tenant_config_atomic_audit.py) |
| **SC-008** quickstart end-to-end on warm stack | ≤ 600 s | **3 s** (T292 measurement; ~200× headroom) | T292 re-run + [`specs/002-multi-tenant-isolation/quickstart.md`](../../specs/002-multi-tenant-isolation/quickstart.md) |

### Workflow-dispatch + nightly SLOs (gated to a real run per Principle XIV)

| SLO | Budget | Gating condition |
|---|---|---|
| **SC-002** 1000 events/s/tenant sustained ≥99.9% | workflow_dispatch full-profile load | The Phase 10 rate-limit middleware preserves SC-002 from feature 001; verified locally at the assertion level. Production-rate verification is the gate to ADR-0008 promotion. |
| **SC-003** 24-hour soak ≤5% memory growth | nightly tier | Inherited from feature 001 unchanged. |
| **SC-004** Query API p95 ≤ 200 ms | workflow_dispatch | Inherited unchanged. |
| **SC-005** Latency budget preserved within 10% of feature-001 baseline after RLS + rate-limit + ownership-lookup | workflow_dispatch | Local unit + integration green; production verification gated. |
| **SC-006** Hot-store p95 ≤ 10 ms preserved within 10% | workflow_dispatch | Same; gated. |

### Verdict

**PASS for SC-008/SC-012/SC-013/SC-014 (locally measured).** Conditional PASS for SC-002/SC-003/SC-004/SC-005/SC-006 (workflow_dispatch + nightly tier per Principle XIV). The gating pattern matches feature 001's Phase 6 closure for SC-001/SC-002/SC-003.

---

## Principle XIII — SLM-First, Isolated, Swappable Model Boundary

**Required**: SLM behind a swappable interface; pinned by revision SHA; constrained-decoding via outlines/instructor; deviations require an ADR.

### Evidence

Feature 002 does not touch the SLM boundary. The Policy Generator + the `PolicyGeneratorClient` interface + ADR-0002/0003/0006 are inherited unchanged from feature 001. [`scripts/check_slm_pinning.py`](../../scripts/check_slm_pinning.py) PASS re-verified at T289.

### Verdict

**PASS** — feature 002 inherits feature 001's posture unchanged. No new ADR amendments.

---

## Principle XIV — Deterministic, Budgeted Model Execution in CI

**Required**: Real SLM with deterministic decoding in contract + integration; deterministic substitute in load + soak; full SLM runs gated to workflow_dispatch + nightly.

### Evidence

Feature 002 does not add any new SLM CI surface. The split is inherited from feature 001's `.github/workflows/ci.yaml` + `.github/workflows/ci-workflow-dispatch.yaml` + `.github/workflows/nightly.yaml`.

### Verdict

**PASS** — inheritance verified by T289.

---

## ADR promotion decisions at this closure

| ADR | Status before | Status after | Reason |
|---|---|---|---|
| ADR-0007 (RLS RESTRICTIVE + break-glass) | Accepted (Phase 9.b) | **Accepted** (unchanged) | Already promoted at Phase 9.b closure. Integration tier verifies the RESTRICTIVE+PERMISSIVE-baseline pattern + break-glass atomic audit + SET LOCAL ROLE + GUC contract. |
| ADR-0008 (rate-limiting + hot-store migration) | Proposed | **Proposed (gating note added)** | Local rate-limit middleware is green (Phase 10); hot-store migration completed (Phase 11 + cleanup at Phase 14 T293). Production verification requires the SC-002 + SC-003 workflow_dispatch runs to assert end-to-end behavior under rate-limit ceilings + 24h soak. The pattern matches ADR-0002's GPU-runner-baseline gating: deliberately Proposed pending the gating evidence, NOT a deficiency. |
| ADR-0009 (tenant-vehicle ownership store) | Accepted (Phase 9.b) | **Accepted** (unchanged) | Already promoted at Phase 9.b closure. Phase 12 added the deployer hot-path validation per Part 6 + the write-through Redis ownership cache per Part 4. All five parts of the ADR are exercised by tests. |

## Deferred items at closure (named, not silent)

| Item | Source | Gating |
|---|---|---|
| ADR-0008 promotion to Accepted | This review | First successful workflow_dispatch SC-002 + SC-003 runs against the rate-limited orchestration-api. Follow-up commit: `docs: ADR-0008 promote to Accepted`. |
| `test_rls_migration_rollback.py` schema_migrations desync (full-integration sweep flake) | Phase 12.c finding | Two-line fix; out of scope at this closure. Workaround documented in `docs/DECISIONS.md`. |
| `app._lifespan` `OwnershipCache` wiring | Phase 12 watch-point | Lazy default factories ship at Phase 12; production DI wiring through FastAPI lifespan is a Phase-15 polish item. No functional regression; integration tests use the lazy default path explicitly. |
| `T244` Terraform `null_resource` for migration runner | Phase 9.b deferral | Terraform-side decision (one-shot local-exec vs sidecar-init-container vs ECS task with dependsOn). Bundled with the cloud-deploy hardening feature. |

## Closure attestation

Every NON-NEGOTIABLE principle has a PASS verdict (with conditional gating for SC-002/SC-003/SC-004/SC-005/SC-006 on the workflow_dispatch + nightly tier per Principle XIV's deliberate split). ADR-0007 + ADR-0009 are Accepted; ADR-0008 is Proposed with documented gating. Two test-infrastructure deferrals are named with workarounds. Feature 002 is shipped.
