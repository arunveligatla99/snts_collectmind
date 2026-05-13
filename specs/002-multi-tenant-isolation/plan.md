# Implementation Plan: Multi-Tenant Isolation

**Branch**: `002-multi-tenant-isolation` | **Date**: 2026-05-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-multi-tenant-isolation/spec.md`

## Summary

Convert every multi-tenant isolation primitive in the CollectMind policy loop from permissive-by-construction to restrictive-by-construction, and prove the conversion with negative-path tests that exercise every cross-tenant attack surface. Tighten Postgres Row-Level Security from `PERMISSIVE` to `RESTRICTIVE` on every tenant-scoped table; add per-tenant ingress rate limiting on `POST /api/v1/findings` and on every `GET /api/v1/...` query endpoint; tighten the Redis hot-store key shape from `vehicle_id:signal_name` to `tenant_id:vehicle_id:signal_name`; tighten the deployment client's tenant scoping with an authoritative ownership lookup that rejects mismatches as a Fatal error class. Introduce the FR-005a break-glass service-principal bypass primitive (operator JWT audience, distinct endpoint) with an atomic `kind=break_glass` audit-row writer. Introduce a Postgres `tenant_config` table for per-tenant rate-limit overrides with a `LISTEN/NOTIFY`-driven cache and an atomic `kind=tenant_config_change` audit-row writer. Introduce the previously-assumed-but-missing `tenant_vehicles` ownership store as a first-class data-model entity in this feature, with a mutable-current-row + append-only-history shape justified in ADR-0009.

Technical approach: extend the existing FastAPI + Pydantic v2 + PostgreSQL 16 + Redis 7 + Kafka + ECS Fargate stack from feature 001. No new runtime dependencies for the runtime path (token-bucket counters via a Redis Lua script, ownership lookup via a write-through Redis cache backed by Postgres); the only new external authority is a second JWT issuer scoped to operator-principals for the break-glass surface (verified by the same `PyJWT`+JWKS pipeline used today). Migrations and new tables ship via the existing `src/collectmind/registry/migrations/sql/` migrator with explicit forward + backward sql files. Three new ADRs at status `Proposed` land alongside the plan: ADR-0007 (RLS hardening + break-glass), ADR-0008 (per-tenant rate limiting + hot-store migration mechanism), ADR-0009 (tenant-vehicle ownership store + mutability model). The plan resolves the three load-bearing decisions called out at session kickoff (ownership store mutability, hot-store migration mechanism, break-glass surface) in [`research.md`](./research.md) and propagates each into the corresponding artifact.

## Technical Context

**Language/Version**: Python 3.11.9 (retained from feature 001; pinned in `.python-version`, application `Dockerfile`, and `pyproject.toml`).

**Primary Dependencies** (deltas relative to feature 001):
- Retained: FastAPI, Pydantic v2, LangGraph, httpx, structlog, OpenTelemetry SDK with OTLP exporter, PyJWT with JWKS caching, `outlines==1.2.13`, vLLM, llama.cpp.
- New runtime: `redis>=5.0` (already present; this feature adds a Redis Lua script for the token-bucket counter — `src/collectmind/ratelimit/token_bucket.lua` — but no new Python dependency).
- New runtime: `asyncpg` `LISTEN/NOTIFY` consumer task for the `tenant_config` reload signal (already present in dep set; new code path only).
- New CI: no new dependencies. The negative-path schemathesis suite reuses the existing fuzzer and stateful link-following.

**Storage** (deltas relative to feature 001):
- Postgres 16 + TimescaleDB: retained. New tables in this feature: `tenant_config` (per-tenant rate-limit overrides), `tenant_vehicles` (current vehicle→tenant ownership, RESTRICTIVE RLS, exactly one row per `vehicle_id`), `tenant_vehicles_history` (append-only transfer log; RESTRICTIVE RLS keyed by `tenant_id` on each historic owner so neither prior nor new tenant can read the other's transfer attribution).
- RLS migration: every existing tenant-scoped table (`collection_policies`, `deployment_targets`, `audit_events`, `telemetry_observations`, `erasure_requests`, plus the new `tenant_config`, `tenant_vehicles`, `tenant_vehicles_history`) drops its `PERMISSIVE` policy and adds a `RESTRICTIVE` policy that defends against both the missing-GUC (`current_setting('app.tenant_id', true) IS NULL`) and wrong-GUC cases.
- Redis 7: retained. Key shape transitions from `vehicle_id:signal_name` to `tenant_id:vehicle_id:signal_name`. Migration mechanism: TTL-driven natural rollover (see [`research.md`](./research.md) §3); writers switch to the new key shape at deploy-cutover, readers prefer the new key and fall back to the legacy key for the duration of the existing 24-hour TTL. New per-tenant counter keys for the token bucket: `ratelimit:{tenant_id}:{endpoint}:{bucket_id}`.
- New audit row kinds: `break_glass`, `tenant_config_change`, `deployment_rejected`, `vehicle_assignment_change`. Same `audit_events` table; the existing audit writer is extended to honor the FR-017a minimum field set for each new kind.

**Testing**: retained from feature 001. New tiers added to existing CI workflows (no new workflow files):
- Unit: token-bucket Lua semantics under hypothesis, RLS policy fixtures under embedded Postgres, JWT-issuer-discrimination tests, tenant-config cache-reload tests, ownership-cache-eviction tests, audit-row minimum-field-set assertions for each new kind.
- Contract: `schemathesis` negative-path suite (wrong-tenant token → 404 on every endpoint declared in the OpenAPI surface); break-glass endpoint contract test (operator JWT → 200 + audit row; tenant JWT → 401); `tenant_config` self-introspection endpoint contract test.
- Integration: end-to-end cross-tenant attack scenarios on the real local stack; noisy-neighbor load on two tenants under the smoke profile; RLS rollback dry-run (forward + backward) executed against a testcontainer Postgres; hot-store key-shape coexistence under the TTL rollover window.
- Load: extend `tests/load/locustfile_smoke.py` with a `MultiTenant` user class that bursts tenant-A while sustaining tenant-B; pin the SC-003 ≥ 80%-rejection and SC-004 zero-degradation assertions in the locust quitting hooks.

**Target Platform**: retained from feature 001. Local Compose stack is extended to provision a second JWT issuer container (lightweight static-signer Docker image) bound under the Compose profile `operator-issuer`, so the foundation smoke can exercise the break-glass surface without AWS in scope.

**Project Type**: cloud control-plane web service with multiple internal microservices. No new microservice; this feature adds middleware, handlers, and migrations to the existing orchestration-api service.

**Performance Goals** (binding; see Spec §Success Criteria + feature 001 inherited SLOs):
- Preserve every feature-001 SC within 10% of its baseline after the rate-limit middleware, the RESTRICTIVE RLS policies, and the ownership-lookup hot path are introduced (Spec SC-005, SC-006).
- Token-bucket decision: p99 < 1 ms (the Lua script runs in a single Redis round trip; budget consumed by the middleware as a whole must keep the orchestration API's per-request p99 inside Principle XI's hot-store-read ceiling).
- Ownership lookup at deployment time: p99 < 5 ms (Redis cached, Postgres backed); the deployer hot path is OK with a single additional round trip.
- `tenant_config` reload: cache TTL ≤ 5 s; `LISTEN/NOTIFY`-driven invalidation MUST land within 1 s of the configuration write commit so noisy-neighbor mitigation is responsive.
- Negative-path contract suite wall-clock: ≤ 5 min added to PR-tier CI (SC-009 budget retained).

**Constraints** (deltas from feature 001):
- Principle X is the binding contract for this feature. Every isolation primitive is enforced at all three layers (API gateway, DB row, deployment client) per the constitution; the readiness review at closure walks each layer with a named artifact.
- The break-glass bypass primitive is in scope; the operator-facing surface (UI, CLI, escalation workflow) is explicitly out of scope (Spec §Explicitly out of scope).
- Failure-closed posture on Redis unavailability for rate limiting (ADR-0008): when the token-bucket Redis script fails or times out, the middleware MUST reject with 503 (not silently allow). Justification: the rate limit is a security primitive for shared-infra protection; failing open under Redis outage would let a noisy tenant escape detection precisely when the operator most needs the gate to hold.
- Tenant-vehicle ownership is mutable with append-only history (ADR-0009). The deployer hot path always reads the *current* row from `tenant_vehicles`; the history table is operator-readable only via the break-glass primitive (per FR-005a) or via operator-issuer-scoped admin endpoints (out of scope; future feature).

**Scale/Scope**:
- Feature 001's scale assumptions retained (1,000 events/s/tenant).
- Multi-tenant scope: the test bar exercises ≥ 2 tenants concurrently (US1's negative-path suite + US2's noisy-neighbor profile). The data model supports an unbounded tenant set; the operational quickstart provisions exactly 2 tenants for the foundation smoke.
- `tenant_config` row count = tenants with overrides (expected ≪ total tenants; most tenants run with the FR-012 defaults).
- `tenant_vehicles` row count = total fleet under management (expected order 10⁴–10⁶ at maturity; current row is a single read).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Gates evaluated against [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) v1.0.1.

| # | Principle | Status | Justification |
|---|---|---|---|
| I | Production-Grade by Default | PASS | Every artifact in this feature is held to the feature-001 closure bar (per [docs/runbook/feature-001-readiness-review.md](../../docs/runbook/feature-001-readiness-review.md)). The readiness review for feature 002 will walk every NON-NEGOTIABLE with a named artifact. |
| II | No Mocked Subsystems Where a Real One Is Feasible | PASS | Real Postgres (RLS migrations + token-bucket override storage), real Redis (token-bucket Lua + ownership cache + key-shape rollover), real Kafka (untouched), real second JWT issuer container (Compose profile `operator-issuer`) for the break-glass surface. No mocked subsystems introduced. |
| III | No TODO, No FIXME, No Deferred Work in Shipped Code | PASS | Feature-001 CI guard `scripts/check_no_todo_fixme.py` retained; this feature's PRs are gated by it. Two named follow-ups from the spec (the operator-facing UI/CLI surfaces for break-glass and tenant management) live in Spec §Explicitly out of scope, not as TODOs in code. |
| IV | Tests Are Load-Bearing (NON-NEGOTIABLE) | PASS | Negative-path contract + integration suites are the primary deliverable. 85% coverage floor retained (will be enforced by `pytest-cov --cov-fail-under=85` per `pyproject.toml`). FR-027 ships a meta-test that fails the build when the negative-path suites are bypassed (RLS disabled or rate-limit middleware removed). |
| V | Observability Is a Functional Requirement | PASS | New Prometheus metrics (`collectmind_ratelimit_decision_total{tenant_id,endpoint,decision}`, `collectmind_break_glass_total{operator_subject,reason}`, `collectmind_tenant_config_change_total{tenant_id}`, `collectmind_cross_tenant_access_attempt_total{endpoint}`, `collectmind_deployment_rejected_total{reason}`); per-tenant rate-limit panel on the existing Grafana dashboard; one runbook page per new alert (rate-limit-sustained-throttle, break-glass-invoked, deployment-tenant-mismatch, tenant-config-reload-stalled). PII-strip CI gate (T142 from feature-001 Phase 7) lands before or with this feature per Assumption §8. |
| VI | Reproducible Local Dev and Deployment | PASS | Compose stack adds the `operator-issuer` profile; quickstart is extended with the multi-tenant smoke (two tenants, cross-tenant 404, break-glass invocation, rate-limit smoke). `make up` + `make test` continue to work; new Compose profile is opt-in for the break-glass smoke. |
| VII | CI/CD Gates Merges (NON-NEGOTIABLE) | PASS | No new workflow files. Existing `.github/workflows/ci.yaml` runs the negative-path contract + integration suites on every PR. The token-bucket Lua script + the RLS migrations + the `tenant_config` table land in PR-tier CI under `ci.yaml`'s integration job. SC-009 budget honored (≤ 5 min added to PR-tier wall clock). |
| VIII | Documentation a Stranger Could Follow | PASS | Three new ADRs (0007/0008/0009) at status Proposed. One new runbook page per new alert. Quickstart re-runnable; README updated with a one-line pointer to the multi-tenant smoke (post-implementation Phase 6 closure work). |
| IX | Security as a First-Class Requirement (NON-NEGOTIABLE) | PASS | Second JWT issuer ("operator-issuer") added as a distinct authentication boundary with a different audience claim; verified through the same PyJWT + JWKS pipeline; signing key in AWS Secrets Manager in cloud, in a local file mounted into the Compose container in dev. Threat model at [docs/security/threat-model.md](../../docs/security/threat-model.md) extended with three new STRIDE/LINDDUN threats (rate-limit bypass via authn forgery, break-glass abuse via operator-key compromise, tenant-vehicle ownership-data integrity attack); each new threat mapped to defending FR + verifying test. |
| X | Vehicle Telemetry Data Handling (NON-NEGOTIABLE) | PASS | This feature is the load-bearing cash-out of Principle X. Every isolation control (DB-level RLS, API-level handler scoping, hot-store key shape, deployment-client validation) tightened; readiness review walks each layer. |
| XI | Performance SLOs Are Measured, Not Aspired (NON-NEGOTIABLE) | PASS | Spec SC-005/SC-006 explicitly bound the regression budget. Noisy-neighbor profile in load tier exercises SC-003 + SC-004; RLS migration timing pinned in SC-010; ownership-lookup p99 < 5 ms budget recorded in the deployer hot path. |
| XII | Agent Boundaries | PASS | No change to the four-node LangGraph. The deployment-client tenant-scoping check (FR-021) is added inside the deployer node before the outbound call; no new agentic decision points. |
| XIII | SLM-First, Isolated, Swappable Model Boundary (NON-NEGOTIABLE) | PASS | Model boundary untouched in this feature. |
| XIV | Deterministic, Budgeted Model Execution in CI (NON-NEGOTIABLE) | PASS | Model execution untouched. Negative-path suites do not invoke the SLM (they exercise the auth + RLS + handler-scoping + ownership-lookup paths only). |
| XV | Edge-Versus-Cloud Split | PASS | Vehicle-side artifact unchanged. |
| XVI | Contracts Are Machine-Readable and Versioned | PASS | New OpenAPI document `contracts/openapi/audit-admin.v1.yaml` declares the break-glass endpoint as a distinct surface; `contracts/openapi/query-api.v1.yaml` extended with the `GET /api/v1/tenant-config/self` introspection endpoint. AsyncAPI surfaces unchanged. Both contracts versioned (`v1.0.0` to start) with a documented bump policy. |
| XVII | Audit Is a Feature, Not a Log | PASS | Two new audit-row kinds (`break_glass`, `tenant_config_change`) each ship with an atomic-audit pattern (audit row written in the same DB transaction as the operation; transaction rolls back on audit-write failure). Two more kinds (`deployment_rejected`, `vehicle_assignment_change`) land for the deployer-scoping check and the ownership-history trigger. Each new kind's minimum field set is recorded inline in the audit writer and asserted by a unit-tier test. |
| XVIII | Governance and Escalation | PASS | Three new ADRs at status Proposed (0007/0008/0009) record the architectural decisions. No constitution-amendment territory. No deviation from a NON-NEGOTIABLE principle proposed. |

**Gate verdict**: PASS. No deviations to record. Complexity Tracking section is empty.

## Project Structure

### Documentation (this feature)

```text
specs/002-multi-tenant-isolation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── openapi/
│   │   ├── audit-admin.v1.yaml         # NEW: break-glass bypass endpoint
│   │   ├── orchestration-api.v1.yaml   # MODIFIED: 429 response shape; cross-tenant 404 semantics
│   │   └── query-api.v1.yaml           # MODIFIED: GET /api/v1/tenant-config/self; cross-tenant 404 semantics
│   └── asyncapi/                       # UNCHANGED in feature 002
├── checklists/
│   └── requirements.md                 # Phase /speckit-specify output (clarify-resolved)
├── spec.md
└── tasks.md             # Phase /speckit-tasks output (not created here)
```

### Source Code (deltas relative to feature 001 layout)

```text
src/collectmind/
├── auth/
│   ├── jwt_verifier.py                 # MODIFIED: dual-issuer support (tenant + operator)
│   ├── operator_principal.py           # NEW: operator-principal extractor + audience check
│   └── dependencies.py                 # MODIFIED: `authenticated_operator_principal` dep
├── ratelimit/                          # NEW package
│   ├── middleware.py                   # FastAPI middleware; token-bucket call + 429 emit
│   ├── token_bucket.lua                # Redis Lua script (atomic check-and-deduct)
│   ├── config_cache.py                 # In-process cache for tenant_config with LISTEN/NOTIFY consumer
│   └── metrics.py                      # Prometheus metric registrations
├── registry/
│   ├── audit.py                        # MODIFIED: new audit-row kinds (break_glass, tenant_config_change, deployment_rejected, vehicle_assignment_change)
│   ├── audit_admin.py                  # NEW: break-glass query primitive + atomic audit writer
│   ├── tenant_config.py                # NEW: tenant_config CRUD (service-principal-only writes; tenant-scoped reads)
│   ├── tenant_vehicles.py              # NEW: tenant_vehicles read primitive; ownership lookup
│   └── migrations/sql/
│       ├── 011_rls_restrictive.up.sql     # NEW: forward migration (PERMISSIVE → RESTRICTIVE)
│       ├── 011_rls_restrictive.down.sql   # NEW: backward migration
│       ├── 012_tenant_config.up.sql       # NEW: tenant_config table + RLS + LISTEN/NOTIFY trigger
│       ├── 012_tenant_config.down.sql
│       ├── 013_tenant_vehicles.up.sql     # NEW: tenant_vehicles + tenant_vehicles_history + RLS + transfer triggers
│       └── 013_tenant_vehicles.down.sql
├── cache/
│   ├── hot_store.py                    # MODIFIED: new key-shape (tenant-scoped); legacy-fallback read for TTL rollover window
│   └── ownership_cache.py              # NEW: write-through Redis cache for tenant_vehicles lookup
├── deployer/
│   └── tenant_scope_check.py           # NEW: deployment-client tenant-vehicle ownership re-validation
├── audit_admin/                        # NEW: break-glass FastAPI router (distinct from query router)
│   └── api.py
├── observability/
│   └── metrics.py                      # MODIFIED: new metrics + tenant_id label conventions
└── app.py                              # MODIFIED: middleware wiring; new router registration; second JWKS bootstrap

contracts/openapi/
├── audit-admin.v1.yaml                 # NEW
├── orchestration-api.v1.yaml           # MODIFIED
└── query-api.v1.yaml                   # MODIFIED

infra/
├── compose/
│   ├── docker-compose.yaml             # MODIFIED: profile `operator-issuer`
│   └── operator-issuer/                # NEW Compose service (static JWT signer)
│       ├── Dockerfile
│       └── jwks.json                   # Local-dev signing keypair
└── terraform/
    ├── secrets/main.tf                 # MODIFIED: operator JWKS signing key entry
    └── data/main.tf                    # MODIFIED: new tables shipped via the existing migrator

observability/
├── grafana/dashboards/
│   └── collectmind.json                # MODIFIED: per-tenant rate-limit panel; break-glass panel
├── prometheus/
│   └── rules.yaml                      # MODIFIED: new alerts (sustained-throttle, break-glass-invoked, deployment-tenant-mismatch)
└── runbooks/
    ├── ratelimit-sustained-throttle.md # NEW
    ├── break-glass-invoked.md          # NEW
    ├── deployment-tenant-mismatch.md   # NEW
    └── tenant-config-reload-stalled.md # NEW

docs/adr/
├── 0007-rls-restrictive-and-break-glass.md       # NEW (Proposed)
├── 0008-per-tenant-rate-limiting.md               # NEW (Proposed)
└── 0009-tenant-vehicle-ownership-store.md         # NEW (Proposed)

tests/
├── unit/
│   ├── test_token_bucket_lua.py        # NEW: hypothesis-based property tests
│   ├── test_audit_kinds.py             # NEW: minimum field set per new kind
│   ├── test_operator_principal.py      # NEW: dual-issuer discrimination
│   ├── test_tenant_config_cache.py     # NEW: LISTEN/NOTIFY reload semantics
│   └── test_ownership_cache.py         # NEW: write-through + invalidation
├── contract/
│   ├── test_negative_path_cross_tenant.py  # NEW: schemathesis with wrong-tenant tokens
│   ├── test_audit_admin_contract.py        # NEW: break-glass endpoint
│   └── test_tenant_config_self_contract.py # NEW: self-introspection endpoint
├── integration/
│   ├── test_rls_restrictive.py             # NEW: missing-GUC + wrong-GUC defense-in-depth
│   ├── test_rls_migration_rollback.py      # NEW: forward + backward, ≤30s SC-010 budget
│   ├── test_break_glass_atomic_audit.py    # NEW: bypass + audit row in same txn (SC-013)
│   ├── test_tenant_config_atomic_audit.py  # NEW: override + audit row in same txn (SC-014)
│   ├── test_hot_store_key_rollover.py      # NEW: dual-shape read coexistence
│   ├── test_deployment_tenant_scope.py     # NEW: cross-tenant deployment rejected fatally
│   └── test_negative_path_e2e.py           # NEW: end-to-end cross-tenant scenarios
└── load/
    └── locustfile_smoke.py             # MODIFIED: MultiTenant user class; SC-003 + SC-004 quitting hooks
```

**Structure Decision**: Extend the existing feature-001 single-repo, multi-module Python layout (`src/collectmind/`, `contracts/`, `infra/`, `observability/`, `tests/`). No new top-level packages outside `src/collectmind/`. Three new packages inside `src/collectmind/` — `ratelimit/`, `audit_admin/`, `cache/ownership_cache.py` — and four new module-level files in existing packages (`registry/audit_admin.py`, `registry/tenant_config.py`, `registry/tenant_vehicles.py`, `deployer/tenant_scope_check.py`). The break-glass surface lives in `src/collectmind/audit_admin/` and is wired into `app.py` as a distinct FastAPI router with its own dependency (`authenticated_operator_principal`); this segregation is the **compile-time** guard against accidental bypass invocation from the regular audit-query path (ADR-0007 §Decision).

## Complexity Tracking

> Constitution Check passed without violations. No entries.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| (none) | | |
