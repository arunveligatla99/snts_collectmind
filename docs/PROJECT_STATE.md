# Project State — CollectMind

**Updated**: 2026-05-11
**Branch**: `002-multi-tenant-isolation`
**Constitution**: v1.0.1 at `.specify/memory/constitution.md`
**Status**: **Feature 001 — `policy-loop-vertical-slice` — is shipped** (commits `990b437` + `a49939e`). Closure artifact: [`docs/runbook/feature-001-readiness-review.md`](runbook/feature-001-readiness-review.md). **Feature 002 — `multi-tenant-isolation` — PLAN COMPLETE; tasks generated** (commits `d085f19` spec/clarify + `d4c83c9` plan/ADRs; tasks at `specs/002-multi-tenant-isolation/tasks.md`). ADRs 0007/0008/0009 Proposed; promote to Accepted at feature-002 closure.

## Phase status (feature 002 — PLAN COMPLETE; implementation not started)

| Phase | Range | Status | Anchor commit |
|---|---|---|---|
| Phase 8: Setup + Foundational (T200–T211) | Compose `operator-issuer` profile, dual-issuer JWT verifier, audit writer extension, migrations 011-014 (RLS RESTRICTIVE, tenant_config, tenant_vehicles + history, audit-events UNIQUE constraint), contracts mirroring | **Not started** | — |
| Phase 9: US1 — Tenant data isolated end-to-end (T220–T245) | Red-phase contract + integration + unit tests; RLS migration; break-glass router + atomic audit; tenant_config + tenant_vehicles repositories; cross-tenant 404 collapse | **Not started** | — |
| Phase 10: US2 — Noisy-neighbor rate limiting (T246–T263) | Token-bucket Lua, middleware, config_cache with LISTEN/NOTIFY, failure-closed posture, defaults, metrics, runbooks, Grafana panels | **Not started** | — |
| Phase 11: US3 — Hot-store key tenancy (T264–T271) | Key-shape transition (TTL-driven natural rollover); fallback-read branch; legacy-shape Fatal guard | **Not started** | — |
| Phase 12: US4 — Deployment-client tenant scoping (T272–T279) | ownership_cache, tenant_scope_check, deployer wiring + Fatal class, deployment-rejected audit row, alert routing | **Not started** | — |
| Phase 13: Observability + operational surface (T280–T284) | Prometheus rules.yaml + Grafana panels + Alertmanager + runbook completeness gate extension | **Not started** | — |
| Phase 14: Polish + closure (T285–T296) | Coverage sweep; ruff + mypy strict; OpenAPI dump diff; threat model extension; T142 PII-strip CI gate; quickstart re-run; readiness review; ADR promotion; one-time-cleanup PR | **Not started** | — |

Plan-output artifacts at [`specs/002-multi-tenant-isolation/`](../specs/002-multi-tenant-isolation/): spec.md (commit `d085f19`), plan.md, research.md, data-model.md, contracts/, quickstart.md (all commit `d4c83c9`). Tasks file: [`tasks.md`](../specs/002-multi-tenant-isolation/tasks.md). Three ADRs (`0007`/`0008`/`0009`) at status Proposed under [`docs/adr/`](adr/).

## Phase status (feature 001 — all phases closed)

| Phase | Range | Status | Anchor commit |
|---|---|---|---|
| Phase 1: Setup (T001–T019) | Repo scaffolding, tooling, Compose stack | **Complete** | `50ade89` |
| Phase 2: Foundational (T020–T047, gap at T036) | VSS pin, weight manifest, migrations, OAuth2 verifier, OTel, Kafka topics, error model, runbook stubs, contracts mirrored | **Complete** | `50ade89` |
| Phase 3: US1 — Operator end-to-end policy loop (T048–T104) | Tests in red phase, then full US1 implementation | **Complete** | `b9fddc8` (impl), `9c4bd7d` (tests red phase), `7dd2723` (verification fixes), `d5f4aa5` (ADR-0006 + startup guard) |
| Phase 4: US2 — On-call observes pipeline (T105–T115) | Dashboard JSON, alert rules, runbook pages, alert-rule parity gate, Alertmanager + local webhook | **Complete** | `d80fc84` (impl), `3266b13` (tests red phase), `c443e2c` (closure docs) |
| Phase 5: US3 — Reviewer trusts the system (T116–T133) | Locust load, CI workflows, Trivy + Syft + gitleaks, custom guards, full Terraform module set, threat model, README polish | **Complete** | `fe9eb41` (impl), `237d122` (closure docs) |
| Phase 6: Polish & closure (T134–T141) | Coverage sweep to 86.24%, ruff + mypy strict clean, dashboard-lag SLO measured, ADR-0002 eval baseline gating note, /docs cross-link, quickstart re-run, SPECKIT block verified, production-readiness review | **Complete** | `990b437` (impl), `a49939e` (closure docs) |

**Feature 001 closed.** T142 (PII-strip CI gate, SC-007) is intentionally deferred to Phase 7 per the user's explicit Phase 6 task-set (`T134–T141` only).

T036 is intentionally absent (build-tooling gate moved to `scripts/check_runbook_completeness.py` at T113; see `docs/DECISIONS.md`).

## Final test bar — feature 001

| Tier | Pass | Fail | Skip | Wall |
|---|---|---|---|---|
| Unit | 214 | 0 | 0 | 5 s |
| Contract | 41 | 0 | 0 | ~200 s |
| Integration | 14 | 0 | 0 | ~225 s |
| Load (smoke, local) | 280 reqs, 0 failures, p50 = 50 ms | n/a | n/a | 60 s |
| **Coverage** | **86.24%** | n/a | n/a | n/a |

Plus every CI guard green locally:
- `ruff check` + `ruff format --check` — code quality (Principle IV / code standards)
- `mypy --strict` — typing (Principle IV / code standards)
- `scripts/check_no_todo_fixme.py` — Principle III
- `scripts/check_slm_pinning.py` — Principle XIV + ADR-0002
- `scripts/check_runbook_completeness.py` — FR-022
- `python -m collectmind.openapi.dump` diff vs `docs/api/openapi.yaml` — T132

## Recorded measurements (from real local runs, no fabrication)

| What | Value | Budget | Headroom | Source |
|---|---|---|---|---|
| Dashboard ingest-to-Prometheus visibility (SC-006), max of 5 runs | **2.11 s** | 10 s | ~5× | T136, `observability/runbooks/slo-006-dashboard-lag.md` |
| Dashboard ingest-to-Prometheus visibility (SC-006), mean | 1.98 s | 10 s | ~5× | T136 |
| Quickstart end-to-end (SC-008), warm Compose stack | **27.32 s** | 600 s | ~22× | T139, `docs/runbook/feature-001-readiness-review.md` |
| Coverage (Principle IV) | **86.24%** | 85% | +1.24 pp over floor | T134, `pyproject.toml` |
| Smoke load — local (T134/T116) | 280 reqs / 0 failures / p50 50 ms in 60 s | SC-001 p50 4 s | ~80× | T134, T116 |

Measurements that require workflow-dispatch / nightly runs (SC-001 p95 12 s under SC-002 load; SC-002 1000 events/s/tenant for 30 min ≥99.9% success; SC-003 24-hour soak memory growth ≤5%, error rate ≤0.1%) are gated to `.github/workflows/ci-workflow-dispatch.yaml` and `.github/workflows/nightly.yaml` per Principle XIV; the assertions are enforced inside the Locust quitting hooks (`tests/load/locustfile_full.py`, `tests/load/locustfile_soak.py`) plus the nightly workflow's post-run RSS-growth check.

## Stack-up

```bash
docker compose -f infra/compose/docker-compose.yaml up -d
until curl -fsS http://localhost:8081/ready >/dev/null 2>&1; do sleep 2; done && echo READY
```

Endpoints: orchestration/query API <http://localhost:8081>; Grafana <http://localhost:3000>; Prometheus <http://localhost:9090>; Alertmanager <http://localhost:9093>; local webhook receiver <http://localhost:9099>.

## Smoke test

See [`specs/001-policy-loop-vertical-slice/quickstart.md`](../specs/001-policy-loop-vertical-slice/quickstart.md). T139 re-run measured 27.32 s end-to-end on a warm stack against the SC-008 600 s budget.

## Run tests

```bash
PYTHONPATH=src pytest tests/unit -q                          # 214 tests, ~5 s, coverage gate ≥85%
PYTHONPATH=src pytest tests/contract -q --no-cov             # 41 tests, ~200 s
PYTHONPATH=src pytest tests/integration -q --no-cov          # 14 tests, ~225 s
python scripts/check_runbook_completeness.py                 # T113 + T106
python scripts/check_no_todo_fixme.py                        # T125
python scripts/check_slm_pinning.py                          # T126
python scripts/check_secrets.py                              # T127 (needs gitleaks on PATH)
ruff check && ruff format --check                            # T135 part 1
mypy src/collectmind                                         # T135 part 2
```

## What is next — Phase 7 (post-feature-001) and feature 002

**Three named Phase 7 follow-ups inherited from Phase 6 closure**:

| Item | Reason | Gating condition |
|---|---|---|
| **ADR-0002 eval-suite baseline + promotion to Accepted** | Closure session ran on a workstation without `nvidia-smi`; per Phase-6 instruction no baseline numbers fabricated. | First successful workflow_dispatch invocation of `.github/workflows/ci-workflow-dispatch.yaml` `eval-suite` job on a `[self-hosted, gpu]` runner. Lands as the follow-up commit `docs: ADR-0002 record eval baseline`. |
| **SC-009 rolling-5-PR wall-clock window logic** | Needs at least one real PR-tier CI run as input; pre-emptive aggregator is speculative. | First PR-tier `ci.yaml` invocation. Lands as a small `scripts/ci_wall_clock_window.py` follow-up if SC-009 starts trending toward 18 min. |
| **T142 PII-strip CI gate (closes SC-007)** | Excluded from Phase 6 per user's explicit `/speckit.implement T134-T141` instruction. The structlog `_pii_processor` exists at `src/collectmind/observability/logging.py`; the CI side at `scripts/check_log_pii.py` lands in the same Phase-7 PR. | Phase 7 work item. |

**Next feature: `002-multi-tenant-isolation`**. Not yet started. When `/speckit-specify 002-multi-tenant-isolation` begins:

1. Create `specs/002-multi-tenant-isolation/` with spec.md, plan.md, research.md, data-model.md, contracts/, quickstart.md, tasks.md, checklists/.
2. Update the SPECKIT block in `CLAUDE.md` to point at the new directory.
3. Re-target the `docs/TASKS.md` alias to `specs/002-multi-tenant-isolation/tasks.md`.
4. Open a new phase table in this `PROJECT_STATE.md` keeping the feature-001 table as a closed historical record.

Feature 002's scope per Phase 1's plan: tighten RLS from permissive to restrictive on every tenant-scoped table; add per-tenant rate limiting at ingress; tighten the Redis hot-store key shape from `vehicle_id:signal_name` to `tenant_id:vehicle_id:signal_name`; tighten the deployment client's tenant scoping. The composite finding key `(tenant_id, finding_id)` and the JWT `tenant_id` claim already exist from day one per Clarifications Q1.

## Feature 002 deferred items (named; not silent)

| Item | Source | Reason / Gating condition |
|---|---|---|
| **T244 Terraform `null_resource` for migration runner invocation** | `specs/002-multi-tenant-isolation/tasks.md` Phase 9.b T244 | Phase 9.b shipped the migration runner as a Python module (`src/collectmind/registry/migrations/runner.py`) with an opt-in startup hook in `app.py` (`MIGRATIONS_AUTO_APPLY=true`). The Terraform `null_resource` that invokes the runner from CI/CD against the deployed RDS Postgres is deferred to Phase 14 polish — it requires a Terraform-side decision (one-shot `local-exec` vs sidecar-init-container vs ECS task with `dependsOn`) that's better made alongside the readiness review than mid-implementation. Gating: lands in Phase 14 as part of T294's readiness review. |
| **Operator-issuer JWKS host-DNS resolution in unit tests** | `tests/unit/test_operator_principal.py` (2 skipped tests) | Host-side Python can't resolve `operator-issuer:8088` (the Compose-internal hostname). 2 unit tests skipped with explicit reason; refactor to FastAPI TestClient + in-memory JWKS lands in Phase 14 polish alongside the readiness review. Gating: Phase 14 polish; not a security regression (the same property is exercised live via the running orchestration-api in T232). |

## What is deferred (named gaps; not silent)

| Item | Source | Reason |
|---|---|---|
| **Audit `UNIQUE (correlation_id, kind)` constraint + `ON CONFLICT DO NOTHING`** (Flag 9 from Phase 3 spot-check) | `src/collectmind/registry/audit.py` | Requires a migration + integration retest. Lands as a Phase-7-or-later migration ADR. |
| **Dedicated `error JSONB` column on `audit_events`** to replace the `_extras` hack (Flag 10) | `src/collectmind/registry/audit.py`, migration `008_audit_events.sql` | Same Phase-7-or-later migration ADR as Flag 9. |
| **Per-signal grouping in `BrakeWearHypothesisRule`** (MEDIUM flag from Phase 3 spot-check) | `src/collectmind/feedback/evaluator.py` | Not load-bearing for feature 001; the rule gets reworked in feature 004 / 005. |
| **VLLMClient resource leak + missing OTel trace propagation on httpx** (MEDIUM flags) | `src/collectmind/slm/vllm_client.py` | Lands alongside the GPU-tier integration work in feature 005's full SLM gating. |
| **ECS execution role does NOT have Secrets Manager read** (MEDIUM, Phase 5 spot-check) | `infra/terraform/secrets/main.tf` | Deliberate — least-privilege; the task role fetches secrets at runtime. |
| **`outcome` audit row keyed by deployment_id, not by the inbound correlation_id** (observed during T139 quickstart) | `src/collectmind/feedback/worker.py` | By design — `deployment_targets` has no `correlation_id` column. T060 already asserts the 4-kind chain without `outcome`. If feature 002 wants outcome to chain through, add a column + migration. |

## Phase 6 spot-check findings (the four files the user named)

| File | Verdict |
|---|---|
| [`docs/runbook/feature-001-readiness-review.md`](runbook/feature-001-readiness-review.md) | PASS — every NON-NEGOTIABLE walked with named artifact, not "the test passes." |
| [`docs/adr/0002-default-slm-qwen2-5-7b-instruct.md`](adr/0002-default-slm-qwen2-5-7b-instruct.md) | PASS — Status remains `Proposed` with a T137 gating note; baseline numbers NOT fabricated per instruction. |
| Coverage report (`coverage.xml` after Phase 6) | PASS — 86.24%, Principle IV's 85% non-negotiable floor satisfied. |
| [`specs/001-policy-loop-vertical-slice/quickstart.md`](../specs/001-policy-loop-vertical-slice/quickstart.md) after T139 re-run | PASS — 27.32 s end-to-end on a warm Compose stack against the SC-008 600 s budget. |

## Commit chain (feature 001 — closed)

```
a49939e  docs: Phase 6 closure — feature 001 shipped
990b437  feat(001): Phase 6 polish (T134-T141) — closure of feature 001
237d122  docs: Phase 5 closure — tasks, project state, decisions, CLAUDE.md
fe9eb41  feat(001): implement US3 (T116-T133) — CI/CD, IaC, load, threat model
c443e2c  docs: Phase 4 closure — tasks, project state, decisions, CLAUDE.md
d80fc84  feat(001): implement US2 (T110-T115) — dashboard, alerts, runbooks, alertmanager
3266b13  test(001): write US2 tests (red phase, T105-T109)
86618bb  docs: project state, decisions, runbook index, README, CLAUDE.md, task progress at end of Phase 3
d5f4aa5  docs+fix(001): ADR-0006 dev_default rationale + startup guard + vLLM CI decoding-strict check
7dd2723  fix(001): close Phase 3 test bar — schemathesis ASCII semver, path sanitization, VSS leaf names, telemetry policy_ref filter, dev_default candidate signal echo, schemathesis 3.x pin
b9fddc8  feat(001): implement US1 (T065-T104) — models, validator, SLM clients, LangGraph, registry, ingest, query, erasure, simulators, fixture corpus
9c4bd7d  test(001): write US1 tests (red phase, T048-T064)
50ade89  feat(001): scaffold setup and foundational layers (Phases 1-2)
1c1d1bb  docs(tasks): feature 001 task breakdown
00d0a72  docs(plan): feature 001 plan, research, data-model, contracts, quickstart, ADRs 0004/0005
50be93e  docs(spec): integrate clarifications and checklist gaps for feature 001
3575542  docs: add ADR-0003 constrained-decoding library outlines (Accepted)
48501d4  docs: add ADR-0002 default SLM Qwen2.5-7B-Instruct (Proposed)
b021a51  docs: add ADR-0001 VSS v6.0 pin and ADR index
a361d0c  chore: ratify constitution v1.0.0
8a6f0c1  docs: correct Phi-4 license in Principle XIII (v1.0.1)
```
