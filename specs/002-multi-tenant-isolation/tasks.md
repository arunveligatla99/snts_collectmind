---
description: "Task list for feature 002 implementation"
---

# Tasks: Multi-Tenant Isolation

**Input**: Design documents from `/specs/002-multi-tenant-isolation/`
**Prerequisites**: spec.md (✓), plan.md (✓), research.md (✓), data-model.md (✓), contracts/ (✓), quickstart.md (✓), ADR-0007/0008/0009 (✓ Proposed)
**Branch**: `002-multi-tenant-isolation`; commits at start of /speckit.tasks: `d085f19` (spec + clarify) + `d4c83c9` (plan + ADRs)

**Tests**: Mandatory per Constitution Principle IV (Tests Are Load-Bearing, NON-NEGOTIABLE). Test-first posture: every user story opens with a red-phase tests-only commit (sub-phase `*.a`) before its implementation commit (sub-phase `*.b`). Each user story closes with a verification gate sub-phase (`*.c`) running every tier against the real local stack.

**Organization**: Tasks grouped by user story; numbering T200-T299; phases 8-14 (continuing feature 001's space). Each task names its FR / SC / Principle anchor and (where applicable) the file path it produces. Migration tasks name both `*.up.sql` and `*.down.sql`. CI-guard tasks name the workflow file and the script.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Parallelizable (different files, no dependency on incomplete tasks).
- **[Story]**: User story tag (US1–US4). Setup/Foundational and Polish phases carry no story tag.
- File paths absolute relative to repo root.

## Path conventions

Single project with multi-module Python service. Source under `src/collectmind/`. Tests under `tests/`. Contracts under `contracts/` (mirroring `specs/002-multi-tenant-isolation/contracts/`). Infrastructure under `infra/`. Observability under `observability/`. ADRs under `docs/adr/`. Runbook pages under `observability/runbooks/`.

---

## Phase 8: Setup + Foundational (Shared infrastructure for feature 002)

**Purpose**: Compose-profile additions, second JWT issuer, SQL migrations, contracts mirroring, audit writer extension. Blocking prerequisites for every user story.

- [X] T200 [P] Mirror `specs/002-multi-tenant-isolation/contracts/openapi/audit-admin.v1.yaml` into the repo-root `contracts/openapi/audit-admin.v1.yaml` (new file). FR-005a / Principle XVI. <!-- 44f9657 -->
- [X] T201 [P] Merge `specs/002-multi-tenant-isolation/contracts/openapi/query-api-v1.1.0.delta.yaml` additions (new path `/tenant-config/self`; 429 on every existing path; cross-tenant 404 semantics; AuditEvent.kind widened with `deployment_rejected`) into `contracts/openapi/query-api.v1.yaml`; bump `info.version` to `1.1.0`. FR-006 / FR-013 / Principle XVI. <!-- 44f9657 -->
- [X] T202 [P] Merge `specs/002-multi-tenant-isolation/contracts/openapi/orchestration-api-v1.1.0.delta.yaml` additions (429 on POST `/findings` and POST `/erasure-requests`; 422→404 collapse for payload tenant-id mismatch) into `contracts/openapi/orchestration-api.v1.yaml`; bump `info.version` to `1.1.0`. FR-006 / FR-007 / Principle XVI. <!-- 44f9657 -->
- [X] T203 Create `infra/compose/operator-issuer/` directory with `Dockerfile` (python:3.11-slim base; `python-jose` + a tiny FastAPI app serving `/.well-known/jwks.json` on port 8080) and `jwks.json` (local-dev static keypair; out of git secrets per Principle IX — file is committed because it's dev-only and clearly labeled non-production). Compose service `operator-issuer` added to `infra/compose/docker-compose.yaml` under a new `profiles: [operator-issuer]` section. Principle IX / Principle VI. <!-- 44f9657 -->
- [X] T204 [P] Create `scripts/dev_issue_jwt.py` helper that signs tenant or operator JWTs against the local static keypair. Used by the quickstart at [`specs/002-multi-tenant-isolation/quickstart.md`](./quickstart.md). Principle VI / Principle VIII. <!-- 44f9657 -->
- [X] T205 Migration `012_rls_restrictive.up.sql` + `012_rls_restrictive.down.sql` at `src/collectmind/registry/migrations/sql/`. Drop PERMISSIVE policies; create RESTRICTIVE policies on every existing tenant-scoped table (`diagnostic_findings`, `collection_policies`, `deployment_targets`, `policy_outcomes`, `audit_events`, `telemetry_observations`, `erasure_requests`). Both directions tested by T226 against SC-010 ≤30s budget. FR-001 / FR-002 / FR-003 / FR-004 / Principle X. <!-- 44f9657 -->
- [X] T206 Migration set: `013_audit_kind_widening.up.sql` + `013_audit_kind_widening.down.sql` (widens `audit_events.kind` CHECK constraint to include `break_glass`, `tenant_config_change`, `deployment_rejected`, `vehicle_assignment_change` — prerequisite for every subsequent migration that fires an atomic-audit trigger), followed by `014_tenant_config.up.sql` + `014_tenant_config.down.sql`. The `014` migration creates `tenant_config` table with constraints from [data-model.md §New table: `tenant_config`](./data-model.md), RESTRICTIVE RLS (FR-013a), `tenant_config_change_audit_trigger` writing atomic `kind=tenant_config_change` audit rows, and `tenant_config_notify_trigger` emitting `NOTIFY tenant_config_changed, '<tenant_id>'`. FR-013 / FR-013a / FR-013b / SC-014. <!-- 44f9657 -->
- [X] T207 Migration `015_tenant_vehicles.up.sql` + `015_tenant_vehicles.down.sql`. Creates `tenant_vehicles` + `tenant_vehicles_history` tables per [data-model.md §New table: `tenant_vehicles` + `tenant_vehicles_history`](./data-model.md); RESTRICTIVE RLS keyed by current owner on `tenant_vehicles` and by prior-OR-new owner on `tenant_vehicles_history`; `tenant_vehicles_history_trigger` for append-only transitions; immutability trigger on `tenant_vehicles_history`; `tenant_vehicles_audit_trigger` writing atomic `kind=vehicle_assignment_change` audit rows. FR-021 / FR-023 / ADR-0009. <!-- 44f9657 -->
- [X] T208 Migration `016_audit_events_uniqueness.up.sql` + `016_audit_events_uniqueness.down.sql`. Adds `UNIQUE (correlation_id, kind)` constraint on `audit_events` (closes feature-001 Flag 9 deferral per `docs/DECISIONS.md` 2026-05-09 entry). Audit writer at `src/collectmind/registry/audit.py` extended to use `ON CONFLICT DO NOTHING` on inserts. Principle XVII. <!-- 44f9657 -->
- [X] T209 [P] Extend `src/collectmind/registry/audit.py`'s audit-row writer to accept the four new `kind` values (`break_glass`, `tenant_config_change`, `deployment_rejected`, `vehicle_assignment_change`) and enforce per-kind minimum field sets per [data-model.md §Extended `audit_events.kind` enumeration](./data-model.md). Made green by T230. FR-005b / FR-013b / FR-023 / Principle XVII. <!-- 44f9657 -->
- [X] T210 [P] Create `src/collectmind/auth/operator_principal.py` exporting `OperatorPrincipal` Pydantic v2 model + `authenticated_operator_principal` FastAPI dependency that verifies operator-issuer JWTs (audience `collectmind-operator`). Made green by T232 + T222. FR-005a / ADR-0007 Part 4 / Principle IX. <!-- 44f9657 -->
- [X] T211 [P] Extend `src/collectmind/auth/jwt_verifier.py` to support a second issuer instance bootstrapped from `OPERATOR_ISSUER_URL` + `OPERATOR_ISSUER_AUDIENCE` env vars; reuse existing JWKS caching machinery. Tested by T232. ADR-0007 Part 4 / Principle IX. <!-- 44f9657 -->

**Checkpoint**: Phase 8 complete. Compose stack boots with the `operator-issuer` profile. SQL migrations apply forward + backward. Audit writer accepts the four new kinds. User-story phases can begin.

---

## Phase 9: User Story 1 — Tenant data is isolated end-to-end (Priority: P1) 🎯 MVP

**Goal**: A platform operator onboards a second tenant; no request authenticated as tenant A can read, write, or deploy against tenant-B data through any endpoint under any application-layer failure mode. Negative-path tests prove the property at the contract tier and at the integration tier.

**Independent Test**: Provision tenants A and B, create one resource each, exercise every endpoint with a wrong-tenant token, assert 404 (not 403/422/500). Run the same suite against the DB layer with a wrong-tenant RLS context; assert zero rows.

### Phase 9.a — Red-phase tests (write FIRST, ensure they FAIL before T233)

- [X] T220 [P] [US1] Contract test fanning schemathesis across **the regular OpenAPI surface** (orchestration-api.v1.yaml + query-api.v1.yaml, both at v1.1.0) with wrong-tenant tokens at `tests/contract/test_negative_path_cross_tenant_regular.py`. Asserts every endpoint returns 404; fails the build on any 200/403/422/500 (per FR-025). Runs in `.github/workflows/ci.yaml`'s `contract-tests` job. SC-001 / FR-006 / FR-025 / Principle IV. <!-- 4d18a22 -->
- [X] T221 [P] [US1] Contract test fanning schemathesis across **the audit-admin OpenAPI surface** (audit-admin.v1.yaml — separate document, not merged into query-api) with wrong-audience tokens (tenant JWT presented at the operator endpoint must return 401) at `tests/contract/test_negative_path_cross_tenant_admin.py`. Distinct task from T220 per user implementer note. Runs in `.github/workflows/ci.yaml`'s `contract-tests` job. FR-005a / FR-025 / Principle IV / Principle XVI. <!-- 4d18a22 -->
- [X] T222 [P] [US1] Contract test for the break-glass endpoint (`POST /api/v1/audit/break-glass/query`) at `tests/contract/test_audit_admin_break_glass_contract.py`. Asserts operator JWT → 200 with `kind=break_glass` audit row written; tenant JWT → 401; missing reason_code → 400. FR-005a / FR-005b / SC-013. <!-- 4d18a22 -->
- [X] T223 [P] [US1] Contract test for `GET /api/v1/tenant-config/self` at `tests/contract/test_tenant_config_self_contract.py`. Asserts tenant JWT returns own config row OR FR-012 defaults; tenant cannot read another tenant's config. FR-013 / FR-013a. <!-- 4d18a22 -->
- [X] T224 [P] [US1] Integration test for the RLS missing-context defense at `tests/integration/test_rls_restrictive.py::test_missing_context_returns_zero_rows`. Opens a DB session under the tenant-scoped role with `app.tenant_id` unset; asserts SELECT on every tenant-scoped table returns 0 rows; asserts INSERT/UPDATE/DELETE refused. FR-002 / SC-002 / Principle X. <!-- 4d18a22 -->
- [X] T225 [P] [US1] Integration test for the RLS wrong-context defense at `tests/integration/test_rls_restrictive.py::test_wrong_context_returns_zero_rows`. Sets `app.tenant_id` to tenant A; targets tenant B's row by primary key; asserts 0 rows even though the row exists. FR-003 / SC-002 / Principle X. <!-- 4d18a22 -->
- [X] T226 [P] [US1] Integration test for `SET LOCAL`-based GUC reset across transaction boundaries at `tests/integration/test_rls_restrictive.py::test_stale_gucs_fail_closed`. Verifies connection-pool reuse cannot leak rows from a stale GUC (Spec Edge Case 3). ADR-0007 Part 3 / Principle X. <!-- 4d18a22 -->
- [X] T227 [P] [US1] Integration test for the RLS migration forward + backward rollback at `tests/integration/test_rls_migration_rollback.py`. Asserts both directions complete ≤30 s; asserts rolling-deploy safety (RESTRICTIVE ⊂ PERMISSIVE visibility) by holding a mixed-policy fleet during the migration. SC-010 / FR-004 / ADR-0007 Part 2. <!-- 4d18a22 -->
- [X] T228 [P] [US1] Integration test for atomic break-glass audit at `tests/integration/test_break_glass_atomic_audit.py`. Drives the bypass once per reason code; queries `audit_events` for the matching `kind=break_glass` row; negative-path: injects an audit-write failure, asserts the SELECT result is discarded and no rows are returned to the caller. SC-013 / FR-005b. <!-- 4d18a22 -->
- [X] T229 [P] [US1] Integration test for atomic `tenant_config` audit at `tests/integration/test_tenant_config_atomic_audit.py`. Drives `INSERT`, `UPDATE`, `DELETE` against `tenant_config`; queries `audit_events` for matching `kind=tenant_config_change` rows; negative-path injects audit-write failure, asserts the configuration write is rolled back. SC-014 / FR-013b. <!-- 4d18a22 -->
- [X] T230 [P] [US1] Unit tests for audit-row minimum field sets per new kind at `tests/unit/test_audit_kinds.py`. One parametrized test per kind (`break_glass`, `tenant_config_change`, `deployment_rejected`, `vehicle_assignment_change`); asserts writer rejects rows missing any required field. Made green by T209. FR-005b / FR-013b / FR-023. <!-- 4d18a22 -->
- [X] T231 [P] [US1] Unit test for operator-principal vs tenant-principal JWT discrimination at `tests/unit/test_operator_principal.py`. Operator JWT → operator dependency resolves, tenant dependency raises; tenant JWT → vice versa. FR-005a / ADR-0007 Part 4. <!-- 4d18a22 -->
- [X] T232 [P] [US1] Integration test for the full end-to-end cross-tenant attack surface at `tests/integration/test_negative_path_e2e.py`. Walks every Acceptance Scenario under US1 in [spec.md](./spec.md) against the real local Compose stack with both `operator-issuer` and `default` profiles up. FR-006 / FR-008 / SC-001. <!-- 4d18a22 -->

### Phase 9.b — Implementation (each task names the test it makes green)

- [X] T233 [US1] Apply Phase 8 migration `012_rls_restrictive.{up,down}.sql` via the runner at `src/collectmind/registry/migrations/runner.py`; verify forward + backward against a fresh testcontainer Postgres. Makes T224 + T225 + T227 green. FR-001 / FR-004 / Principle X. <!-- 5429689 -->
- [X] T234 [US1] Create `src/collectmind/registry/tenant_config.py` exposing `TenantConfigRepository` with service-principal-only `upsert` / `delete` and tenant-scoped `get_self`. Wire the `LISTEN/NOTIFY` consumer in a new `src/collectmind/ratelimit/config_cache.py` (Phase 10 lands the consumer logic; this task creates the repository + the read primitives only). Makes T223 green. FR-013 / FR-013a. <!-- 5429689 -->
- [X] T235 [US1] Create `src/collectmind/registry/tenant_vehicles.py` exposing `TenantVehiclesRepository` with current-owner read primitive (`get_owner(vehicle_id) -> tenant_id | None`) and service-principal-only assignment writer. Makes US4's T273 green. ADR-0009. <!-- 5429689 -->
- [X] T236 [US1] Wire the audit writer's `ON CONFLICT DO NOTHING` clause to the new `UNIQUE (correlation_id, kind)` constraint per T208. Makes idempotency under retry safe for all four new kinds. Principle XVII. <!-- 5429689 -->
- [X] T237 [US1] Create `src/collectmind/audit_admin/api.py` exposing the break-glass FastAPI router with handler chain `authenticated_operator_principal` → service-principal Postgres connection → parameterized `WHERE tenant_id = $1 AND correlation_id = $2` SELECT → atomic `kind=break_glass` audit-row write → response. Distinct router with its own `app.include_router(...)` registration in `app.py`. Makes T222 + T228 green. FR-005a / FR-005b / FR-005c / ADR-0007 Part 5 / Principle XVII. <!-- 5429689 -->
- [X] T238 [US1] Wire `authenticated_operator_principal` dependency from T210 into `app.py`; mount the break-glass router with `dependencies=[Depends(authenticated_operator_principal)]` at the router level. Verifies operator JWT audience claim before any handler is reached. Makes T231 green. ADR-0007 Part 4 / Principle IX. <!-- 5429689 -->
- [X] T239 [US1] Apply Phase 8 migration `014_tenant_config.{up,down}.sql` (T206); verify trigger fires on every `INSERT`/`UPDATE`/`DELETE`; verify the atomic-audit pattern aborts the transaction on audit-write failure. Makes T229 green. FR-013b / SC-014. <!-- 5429689 -->
- [X] T240 [US1] Apply Phase 8 migration `015_tenant_vehicles.{up,down}.sql` (T207); verify the `tenant_vehicles_history` immutability trigger refuses UPDATE/DELETE; verify the audit-row trigger fires on every transition. ADR-0009 Part 3. <!-- 5429689 -->
- [X] T241 [US1] Add `GET /api/v1/tenant-config/self` handler under the regular query router; returns the requesting tenant's row or FR-012 defaults if no row exists. Makes T223 green. FR-013 / FR-013a. <!-- 5429689 -->
- [X] T242 [US1] Cross-tenant 404 collapse: extend every existing handler under `src/collectmind/query/api.py`, `src/collectmind/ingest/api.py`, and `src/collectmind/erasure/api.py` to return 404 (not 403/422) when (a) the targeted resource exists but belongs to a different tenant, or (b) the request payload's tenant_id field disagrees with the JWT claim. Makes T220 + T232 green. FR-006 / FR-007 / FR-009. <!-- 5429689 -->
- [X] T243 [US1] Apply Phase 8 migration `016_audit_events_uniqueness.{up,down}.sql` (T208); apply `ON CONFLICT DO NOTHING` clause from T236. Closes feature-001 Flag 9 deferral. Principle XVII. <!-- 5429689 -->
- [X] T244 [P] [US1] Terraform: extend `infra/terraform/secrets/main.tf` with an `aws_secretsmanager_secret` for the operator-issuer signing key; extend `infra/terraform/data/main.tf` to invoke the new migrations (012-016) via the existing migrator's Terraform null_resource. Principle VI / Principle IX. <!-- 5429689 -->

### Phase 9.c — Verification gate

- [X] T245 [US1] Verification gate — **integration tier**. Run the Phase 9.a **contract + integration** tests against the real local Compose stack with both profiles up (`default` + `operator-issuer`): T220, T221, T222, T223 (contract); T224, T225, T226, T227, T228, T229, T232 (integration). Unit tests T230 + T231 run in-process under the standard PR-tier `pytest tests/unit` invocation and are NOT part of the integration closure gate (they were the red phase for the audit-writer + operator-principal modules, but the closure question is "does the system, end-to-end against the real Compose stack, refuse cross-tenant access?"). Assert: 0 failures across the 11 contract + integration tests. Capture wall-clock for SC-009 budget impact. Four-files spot-check at closure on `src/collectmind/audit_admin/api.py`, `src/collectmind/auth/operator_principal.py`, `src/collectmind/registry/audit.py`, `src/collectmind/registry/migrations/sql/012_rls_restrictive.up.sql` per the feature-001 trust-the-gate pattern. Principle IV / Principle VII. <!-- 5429689 -->

**Checkpoint**: US1 complete. Cross-tenant access fails closed at API + DB + audit layers. Break-glass primitive returns audit events under operator audience with atomic audit. MVP achievable from here.

---

## Phase 10: User Story 2 — Noisy-neighbor protection via rate limiting (Priority: P2)

**Goal**: A single tenant bursting above its configured rate limit is throttled with 429 + `Retry-After`; other tenants are unaffected. Failure-closed under Redis unavailability.

**Independent Test**: Set tenant-A's rate limit low; burst above; assert 429 with Retry-After; assert tenant-B parallel traffic stays within p95 latency budget; assert the dashboard panel renders the throttle.

### Phase 10.a — Red-phase tests

- [X] T246 [P] [US2] Property test for `token_bucket.lua` semantics at `tests/unit/test_token_bucket_lua.py` using hypothesis: monotonic refill, burst-capped, refill-amount invariant. Runs against a testcontainer Redis. ADR-0008 Part 2 / Principle IV. <!-- fd16953 -->
- [X] T247 [P] [US2] Contract test for 429 + `Retry-After` response shape at `tests/contract/test_ratelimit_response_contract.py`. Asserts every rate-limited request produces a `RateLimitedError` payload with `retry_after_seconds >= 1`. FR-011. <!-- fd16953 -->
- [X] T248 [P] [US2] Unit test for `tenant_config` cache reload at `tests/unit/test_tenant_config_cache.py`. Simulates `NOTIFY tenant_config_changed` events; asserts the named tenant's entry is invalidated within 1s; asserts TTL fallback (5s) covers NOTIFY-loss. ADR-0008 Part 4. <!-- fd16953 -->
- [X] T249 [P] [US2] Integration test for failure-closed under Redis outage at `tests/integration/test_ratelimit_redis_unavailable.py`. Stops the Redis container; asserts the middleware responds 503 + `Retry-After: 1`; asserts `collectmind_ratelimit_redis_unavailable_total{endpoint}` increments; asserts the regular request never bypasses the limiter. ADR-0008 Part 3. <!-- fd16953 -->
- [X] T250 [P] [US2] Load test additions to `tests/load/locustfile_smoke.py`. New `MultiTenantUser` class; bursts tenant-A at 5× its limit; sustains tenant-B at 0.5× its limit; quitting hooks assert SC-003 (≥80% of A's over-budget rejected) + SC-004 (B's p95 unchanged within 10% of feature-001 baseline). SC-003 / SC-004 / SC-005. <!-- fd16953 -->
- [X] T251 [P] [US2] Unit test for FR-012 default parity at `tests/unit/test_ratelimit_defaults.py`. Asserts `src/collectmind/ratelimit/defaults.py` matches FR-012 verbatim (2000 r/s + burst 4000 inbound; 200 r/s + burst 400 query); asserts no override row in `tenant_config` falls back to defaults. FR-012 / FR-012a. <!-- fd16953 -->
- [X] T252 [P] [US2] Unit test for PII-strip on rate-limit log events at `tests/unit/test_ratelimit_pii_strip.py`. Asserts every structured-log event emitted by the middleware passes the `_pii_processor` from `src/collectmind/observability/logging.py`. SC-007 / FR-014. <!-- fd16953 -->
- [X] T253 [P] [US2] Unit test for FR-017 (authentication-before-rate-limit) at `tests/unit/test_ratelimit_after_auth.py`. Asserts a request that fails JWT verification never increments any tenant's rate-limit counter. FR-017. <!-- fd16953 -->

### Phase 10.b — Implementation

- [X] T254 [US2] Create `src/collectmind/ratelimit/token_bucket.lua` per ADR-0008 Part 2. Atomic check-and-deduct in one Redis round trip; returns `(decision, remaining_or_retry_after_ms)`. Made green by T246. <!-- d4beeaa -->
- [X] T255 [US2] Create `src/collectmind/ratelimit/middleware.py` FastAPI middleware: extract `tenant_id` from verified JWT (after auth); call `token_bucket.lua` with parameters from `config_cache`; on allow → pass through; on reject → return 429 + Retry-After; on Redis failure → return 503 + Retry-After: 1 per failure-closed posture. Made green by T247 + T249. FR-010 / FR-011 / FR-017 / ADR-0008 Part 3. <!-- d4beeaa -->
- [X] T256 [US2] Complete `src/collectmind/ratelimit/config_cache.py` (started in T234). Implement the asyncio `LISTEN/NOTIFY` consumer; LRU cache (size 1024, TTL 5s). Made green by T248. ADR-0008 Part 4. <!-- d4beeaa -->
- [X] T257 [US2] Create `src/collectmind/ratelimit/defaults.py` with FR-012's default values as module-level constants. Made green by T251. FR-012. <!-- d4beeaa -->
- [X] T258 [US2] Create `src/collectmind/ratelimit/metrics.py` registering the Prometheus metrics from ADR-0008 Part 6 (`collectmind_ratelimit_decision_total{tenant_id,endpoint,decision}`, `collectmind_ratelimit_redis_unavailable_total{endpoint}`). Wire into `src/collectmind/observability/metrics.py`'s declared-metric registry so the dashboard contract test (T105 from feature 001) picks them up. Principle V. <!-- d4beeaa -->
- [X] T259 [US2] Wire the middleware into `src/collectmind/app.py` between the auth dependency and every router. Ensure `/health` and `/ready` bypass it per FR-017. <!-- d4beeaa -->
- [X] T260 [US2] Create `observability/runbooks/ratelimit-sustained-throttle.md` with the canonical four sections (Symptoms, Dashboard, Mitigation, Escalation per the T106 + T113 enforcement pattern from feature 001). Inline FR-012a's binding rate-limit-versus-SLO distinction so future operators do not lower the limit to "match the SLO." FR-016 / FR-012a / Principle V. <!-- d4beeaa -->
- [X] T261 [US2] Create `observability/runbooks/ratelimit-redis-unavailable.md` documenting the failure-closed posture, the operator's failover procedure, and the alert routing. ADR-0008 Part 3 / Principle V. <!-- d4beeaa -->
- [X] T262 [P] [US2] Add per-tenant rate-limit panels to `observability/grafana/dashboards/collectmind.json`: `sum by (tenant_id) (rate(collectmind_ratelimit_decision_total{decision="reject"}[1m]))` and the throttle-rate-by-endpoint heatmap. Principle V. <!-- d4beeaa -->

### Phase 10.c — Verification gate

- [X] T263 [US2] Run every Phase 10.a test against the real local stack. Assert: 0 failures; SC-003 + SC-004 quitting hooks green in the smoke load profile. Capture latency-regression measurement against feature-001 SC-001 baseline for SC-005 reporting. Principle IV / Principle XI. <!-- d4beeaa -->

**Checkpoint**: US2 complete. Per-tenant rate limit honored; noisy tenant isolated; Redis-outage failure-closed posture verified.

---

## Phase 11: User Story 3 — Hot-store key tenancy (Priority: P2)

**Goal**: Two tenants on the same VIN cannot collide in the hot store. TTL-driven natural rollover from legacy key shape to tenant-scoped shape.

**Independent Test**: Write tenant-A telemetry under VIN-X; read as tenant-B for the same vehicle/signal; assert cache-miss sentinel.

### Phase 11.a — Red-phase tests

- [X] T264 [P] [US3] Integration test for the new tenant-scoped key shape at `tests/integration/test_hot_store_key_shape.py`. Asserts writes after cutover land at `tenant_id:vehicle_id:signal_name`; asserts reads at the new shape hit; asserts cross-tenant collision impossible by construction. FR-018. <!-- 2c93827 -->
- [X] T265 [P] [US3] Integration test for the TTL-driven rollover at `tests/integration/test_hot_store_key_rollover.py`. Pre-seeds legacy-shape keys under TTL; asserts new-shape reads succeed for new writes; asserts legacy-shape fallback-reads succeed during the rollover window; asserts both branches resolve. ADR-0008 Part 5 / FR-019. <!-- 2c93827 -->
- [X] T266 [P] [US3] Integration test for legacy-shape refusal post-rollover at `tests/integration/test_hot_store_legacy_refused.py`. Once the rollover window closes (test simulates by toggling a flag), any read or write under the legacy shape raises a Fatal error class and produces an audit row. Guards the Phase 14 one-time-cleanup PR. FR-020. <!-- 2c93827 -->

### Phase 11.b — Implementation

- [X] T267 [US3] Update `src/collectmind/cache/hot_store.py`'s `set(tenant_id, vehicle_id, signal_name, value)` to write the new key shape unconditionally. Made green by T264. FR-018 / ADR-0008 Part 5. <!-- f460e7c -->
- [X] T268 [US3] Update `src/collectmind/cache/hot_store.py`'s `get(tenant_id, vehicle_id, signal_name)` to prefer the new key shape and fall back to the legacy shape for the rollover window; gated by a `HOT_STORE_LEGACY_FALLBACK_ENABLED` env var defaulting to `true`. Made green by T265. ADR-0008 Part 5. <!-- f460e7c -->
- [X] T269 [US3] Update `src/collectmind/ingest/telemetry_writer.py` and `src/collectmind/feedback/worker.py` to propagate `tenant_id` to every hot-store call. FR-018 / FR-008. <!-- f460e7c -->
- [X] T270 [US3] Add the post-rollover Fatal-error guard in `hot_store.py`: when `HOT_STORE_LEGACY_FALLBACK_ENABLED=false`, any code path that observes a legacy-shape key raises `LegacyKeyShapeError` (Fatal) and writes an audit row. Made green by T266. FR-020. <!-- f460e7c -->

### Phase 11.c — Verification gate

- [X] T271 [US3] Run every Phase 11.a test against the real local stack with the TTL set to a short value (so the rollover window is testable in seconds). Assert: 0 failures. SC-006 latency budget preserved within 10% of the feature-001 baseline (measured by the existing hot-store-read load profile). SC-006 / Principle IV. <!-- f460e7c -->

**Checkpoint**: US3 complete. Hot-store keys carry tenant prefix; rollover path tested; legacy-shape guard ready for the Phase 14 cleanup PR.

---

## Phase 12: User Story 4 — Deployment-client tenant scoping (Priority: P3)

**Goal**: A policy whose declared tenant doesn't match its target vehicle's owning tenant is refused with a Fatal error class; mismatch is audited; alert fires within 60 s.

**Independent Test**: Construct a policy targeting a vehicle owned by another tenant; attempt deployment; assert no outbound call; assert `kind=deployment_rejected` audit row; assert page-tier alert.

### Phase 12.a — Red-phase tests

- [X] T272 [P] [US4] Integration test for the deployment-client tenant-scope check at `tests/integration/test_deployment_tenant_scope.py`. Walks every Acceptance Scenario under US4. Asserts: (i) matching tenant → outbound call proceeds; (ii) mismatched → Fatal error class raised, no outbound call, `kind=deployment_rejected` audit row written carrying every FR-023 field; (iii) Fatal supersedes Recoverable retry. FR-021 / FR-022 / FR-023. <!-- 707fb55 -->
- [X] T273 [P] [US4] Integration test for SC-012 alert routing at `tests/integration/test_deployment_alert_routing.py`. Drives one mismatched deployment; asserts the Alertmanager-routed page-tier alert lands at the local webhook receiver within 60s. SC-012 (reuses feature-001 T107 alert-routing harness). <!-- 707fb55 -->
- [X] T274 [P] [US4] Unit test for `ownership_cache.py` write-through + invalidation at `tests/unit/test_ownership_cache.py`. Asserts cache miss hits Postgres + populates Redis; cache hit skips Postgres; explicit invalidation on `tenant_vehicles` write clears the affected key. ADR-0009 Part 4. <!-- 707fb55 -->

### Phase 12.b — Implementation

- [X] T275 [US4] Create `src/collectmind/cache/ownership_cache.py` with write-through to Redis (key shape `vehicle_ownership:{vehicle_id}`, TTL 1h, fall-back-open posture on Redis outage). Made green by T274. ADR-0009 Part 4. <!-- e48faed -->
- [X] T276 [US4] Create `src/collectmind/deployer/tenant_scope_check.py` exposing `validate_tenant_scope(policy)` which iterates `policy.target_vehicle_ids`, calls `ownership_cache.get_owner`, and raises `TenantVehicleMismatch` (Fatal class) on mismatch. ADR-0009 Part 6. <!-- e48faed -->
- [X] T277 [US4] Wire `validate_tenant_scope` into `src/collectmind/deployer/node.py` before the outbound `CollectorAIClient.deploy(...)` call; raise Fatal; write `kind=deployment_rejected` audit row carrying FR-023's minimum field set; suppress the existing Recoverable retry posture on Fatal. Made green by T272. FR-021 / FR-022 / FR-023. <!-- e48faed -->
- [X] T278 [US4] Create `observability/runbooks/deployment-tenant-mismatch.md` with the canonical four sections. Names the most-likely operational causes (operator entered wrong VIN in a manual policy injection; vehicle transfer race; corrupted in-flight policy state) and the recovery procedure. FR-024 / Principle V. <!-- e48faed -->

### Phase 12.c — Verification gate

- [X] T279 [US4] Run every Phase 12.a test against the real local stack. Assert: 0 failures; SC-012 alert routing within 60 s. Principle IV / Principle XI. <!-- e48faed -->

**T279 outcome**: 8/8 Phase 12.a tests green against the real local stack — 3 in `test_deployment_tenant_scope.py` (AS-1 / AS-2 / AS-3), 1 in `test_deployment_alert_routing.py` (SC-012 wall-clock within 60 s), 4 in `tests/unit/test_ownership_cache.py`. Phase 9/10/11 regression sweep (16 tests across `test_rls_restrictive`, `test_break_glass_atomic_audit`, `test_negative_path_e2e`, `test_hot_store_*`, `test_ratelimit_redis_unavailable`) green. Full unit suite: 248 pass / 3 skip / 0 fail. Pre-existing test-infrastructure flake in `test_rls_migration_rollback` (manual SQL down/up cycle desynchronizes `schema_migrations` from DB state) surfaced during the full integration regression sweep; not a Phase 12 regression; fix deferred to Phase 14 polish per `docs/DECISIONS.md`.

**Checkpoint**: US4 complete. Deployment-client tenant scoping enforced; mismatch audit chain complete; alert routing verified.

---

## Phase 13: Observability + operational surface (cross-cutting)

**Purpose**: Prometheus alert rules, Grafana panels, Alertmanager severity tiers, runbook completeness, alert-rule parity tests.

- [X] T280 [P] Extend `observability/prometheus/rules.yaml` with **six** new alerts (Phase 13 review split `BreakGlassInvoked` into single-invocation page + `BreakGlassBurstInvocation` critical-tier 5-min rate): `RatelimitSustainedThrottle` (FR-016, page), `RatelimitRedisUnavailable` (ADR-0008 Part 3, page), `BreakGlassInvoked` (SC-013 single-invocation page; preserves `operator_subject` + `reason_code` labels so Alertmanager routes per tuple), `BreakGlassBurstInvocation` (SC-013 burst critical, 5-min rate per operator), `TenantConfigReloadStalled` (SC-014 LISTEN/NOTIFY consumer lag, page), `DeploymentTenantMismatch` (SC-012, page). FR-016 / FR-024 / SC-012 / SC-013 / SC-014. <!-- 1e6f76e -->
- [X] T281 [P] Extend `observability/grafana/dashboards/collectmind-end-to-end.json` with 4 new panels referencing 4 metric series: `collectmind_break_glass_invocation_total` (per operator), `collectmind_deployment_rejected_total` (per reason), `collectmind_cross_tenant_access_attempt_total` (per endpoint; no alert per Phase 13 review), `collectmind_ratelimit_decision_total` (allow/reject per tenant). Three NEW metric series declared in `src/collectmind/observability/metrics.py` plus one gauge (`collectmind_tenant_config_cache_consumer_lag_seconds` for SC-014); `dashboard_provisioner.declared_metric_names()` extended to scan the rate-limit metrics module. Principle V. <!-- 1e6f76e -->
- [X] T282 [P] Extend `tests/unit/test_alert_runbook_parity.py` (feature-001 T106) with `REQUIRED_PHASE_13_ALERTS` (6-name bare-set check) + `test_phase_13_alerts_carry_severity_strictly_pinned` (per-name severity map, page vs critical strictly enforced); `REQUIRED_SLO_TAGS` gains SC-013 + SC-014. Three NEW runbook pages with canonical sections: `break-glass-invoked.md`, `break-glass-burst-invocation.md`, `tenant-config-reload-stalled.md`. Principle V / Principle VIII. <!-- 701f32c, 1e6f76e -->
- [X] T283 [P] Extend `scripts/check_runbook_completeness.py` (feature-001 T113) with bidirectional invariant: free function `find_orphan_runbooks(rules_doc, runbook_dir, whitelist=None)`. CI mode loads whitelist from `observability/runbooks/.orphan-whitelist.yaml` (12 operational-reference docs); synthetic tests pass explicit set. `check()` enforces both directions; CI guard fails on either. Principle VII / Principle VIII. <!-- 1e6f76e -->
- [X] T284 Update `infra/compose/alertmanager.yaml` with top-priority route for `BreakGlassInvoked` that groups by `(alertname, service, operator_subject, reason_code)` with `group_wait=0s` — single-event visibility per FR-005a + Phase 13 review. Default severity-tier routes from feature 001 cover the other 5 alerts. <!-- 1e6f76e -->

**Checkpoint**: Phase 13 closed. 6 alerts in `rules.yaml`; 4 dashboard panels; 3 new runbook pages; bidirectional CI guard green; alertmanager BreakGlassInvoked route lands. Test bar: 259 unit / 3 skip / 0 fail. `scripts/check_runbook_completeness.py` PASS both directions.

---

## Phase 14: Polish + closure

**Purpose**: Coverage sweep, lint, type-check, OpenAPI diff, threat model extension, quickstart re-run, readiness review, one-time-cleanup PR for hot-store legacy-shape fallback branch.

- [ ] T285 Coverage sweep: bring line coverage on the new modules to the 85% Principle IV floor and over. Add unit tests for any uncovered branches in `src/collectmind/ratelimit/`, `src/collectmind/audit_admin/`, `src/collectmind/cache/ownership_cache.py`, `src/collectmind/registry/tenant_config.py`, `src/collectmind/registry/tenant_vehicles.py`. Verify via `pytest --cov=src/collectmind --cov-fail-under=85`. Principle IV (NON-NEGOTIABLE).
- [ ] T286 `ruff check && ruff format --check && mypy --strict src/collectmind` all clean. No new warnings; no `# type: ignore` introduced. Principle IV / project code-quality standards.
- [ ] T287 OpenAPI dump diff: `python -m collectmind.openapi.dump` produces output byte-identical to the canonical `contracts/openapi/orchestration-api.v1.yaml` + `query-api.v1.yaml` + `audit-admin.v1.yaml` (all at v1.1.0 / v1.0.0 respectively). Wired in `.github/workflows/ci.yaml`'s `custom-guards` job. Principle XVI.
- [ ] T288 `scripts/check_no_todo_fixme.py` pass (feature-001 T125). No TODO/FIXME introduced in feature 002. Principle III.
- [ ] T289 `scripts/check_slm_pinning.py` re-verify (feature-001 T126). Feature 002 does not touch the SLM boundary; assert unchanged. Principle XIV.
- [ ] T290 T142 PII-strip CI gate (Phase-7 follow-up from feature 001; upstream dependency of SC-007). If T142 has not landed by the time feature 002 reaches Phase 14, land it here: create `scripts/check_log_pii.py` and wire it into `.github/workflows/ci.yaml`'s `custom-guards` job. Closes feature-001 SC-007 + feature-002 SC-007. Principle V / Principle IX.
- [ ] T291 Extend `docs/security/threat-model.md` with three new STRIDE/LINDDUN threats per plan.md Constitution Check row IX: (i) rate-limit bypass via JWT-issuer forgery; (ii) break-glass abuse via operator-key compromise; (iii) tenant-vehicle ownership-data integrity attack. Each threat names defending FR + verifying test. Principle IX.
- [ ] T292 Re-run [`quickstart.md`](./quickstart.md). Record wall-clock against SC-008 (≤ 10 min). Capture every step's pass/fail in the readiness-review draft. Principle VIII.
- [ ] T293 One-time-cleanup PR: 24 hours after production deploy, remove the `HOT_STORE_LEGACY_FALLBACK_ENABLED` env var + the legacy-shape fallback branch from `src/collectmind/cache/hot_store.py`; assert via `SCAN` against the production Redis that no legacy-shape keys remain; remove T270's Fatal-error guard since the path is now unreachable. Lands as the follow-up commit `feat(002): hot-store legacy-shape cleanup`. ADR-0008 Part 5.
- [ ] T294 Draft `docs/runbook/feature-002-readiness-review.md` mirroring [`docs/runbook/feature-001-readiness-review.md`](../../docs/runbook/feature-001-readiness-review.md). Walk every NON-NEGOTIABLE constitutional principle (IV, VII, IX, X, XI, XIII, XIV) with a named artifact. ADRs 0007/0008/0009 promote from Proposed to Accepted in the same PR. Principle XVIII.
- [ ] T295 Update `docs/PROJECT_STATE.md` to record feature-002 closure: phase table, final test bar, recorded measurements (SC-003, SC-004, SC-005, SC-006 from real local runs; SC-002 sustained at workflow_dispatch tier; SC-013 + SC-014 from integration), deferred items, commit chain. Preserve feature-001's closed historical table.
- [ ] T296 Update `CLAUDE.md` SPECKIT block: feature 002 closed at the new commit; feature 003 starting point identified or left blank pending the next /speckit-specify run. ADR table flips 0007/0008/0009 from Proposed to Accepted.

**Checkpoint**: Feature 002 closed. Readiness review walks every NON-NEGOTIABLE with a named artifact; ADRs Accepted; quickstart re-runnable; CI green; coverage ≥ 85%.

---

## Dependencies

- Phase 8 blocks every other phase.
- Phase 9 (US1) is MVP. Phases 10, 11, 12 depend on Phase 9 (RLS + auth + audit-kind extension are prerequisites).
- Phase 10, 11, 12 are mutually independent and can land in parallel after Phase 9.
- Phase 13 depends on Phases 10 + 12 (observability surfaces metrics and alerts produced by those phases).
- Phase 14 closes everything.

## Parallel-task opportunities

- **Phase 8**: T200/T201/T202/T204/T209/T210/T211 all [P]; T203/T205/T206/T207/T208 are sequential within the migration chain.
- **Phase 9.a**: T220-T232 are all [P] (different files, no inter-test deps); land as a single red-phase commit.
- **Phase 10.a**: T246-T253 all [P].
- **Phase 11.a**: T264/T265/T266 all [P].
- **Phase 12.a**: T272/T273/T274 all [P].
- **Phase 13**: T280/T281/T282/T283 all [P].

## Independent test criteria per story

| Story | Independent test | Spec anchor |
|---|---|---|
| US1 | Provision 2 tenants + 1 resource each; cross-tenant access returns 404 across every endpoint | SC-001, SC-002, SC-013, SC-014 |
| US2 | Tenant-A burst at 5× limit; tenant-B parallel traffic unaffected | SC-003, SC-004, SC-005 |
| US3 | Tenant-A write + tenant-B read on same VIN; tenant-B sees cache miss | SC-006 |
| US4 | Mismatched-policy deployment refused fatally + audited + alerted within 60 s | SC-012 |

## Suggested MVP scope

US1 (Phase 9) is the MVP. With US1 alone, the multi-tenant isolation contract holds (DB-level + API-level + audit-level). US2/US3/US4 add depth (availability protection, hot-store tenancy, egress-side validation) but the core property — "no cross-tenant read or write succeeds" — is in US1.

## Format validation

Every task above carries: `- [ ]` checkbox, `Txxx` task ID in T200-T299, optional `[P]` parallelizable marker, `[USx]` story tag for user-story phases (none for Phase 8/13/14), description with file path or scope, and an anchor to a constitutional principle / FR / SC where applicable. Migration tasks name both `*.up.sql` and `*.down.sql`. CI-guard tasks name the workflow file + the script.

