# Project State — CollectMind

**Updated**: 2026-05-11
**Branch**: `001-policy-loop-vertical-slice`
**Constitution**: v1.0.1 at `.specify/memory/constitution.md`

## Phase status

| Phase | Range | Status | Anchor commit |
|---|---|---|---|
| Phase 1: Setup (T001–T019) | Repo scaffolding, tooling, Compose stack | **Complete** | `50ade89` |
| Phase 2: Foundational (T020–T047, gap at T036) | VSS pin, weight manifest, migrations, OAuth2 verifier, OTel, Kafka topics, error model, runbook stubs, contracts mirrored | **Complete** | `50ade89` |
| Phase 3: US1 — Operator end-to-end policy loop (T048–T104) | Tests in red phase, then full US1 implementation | **Complete** | `b9fddc8` (US1 implementation); `9c4bd7d` (T048–T064 tests red phase); `7dd2723` (Phase 3 verification fixes); `d5f4aa5` (ADR-0006 + startup guard + vLLM CI decoding-strict check) |
| Phase 4: US2 — On-call observes pipeline (T105–T115) | Dashboard JSON, alert rules, runbook pages, alert-rule parity gate, Alertmanager + local webhook | **Complete** | `d80fc84` (US2 implementation); `3266b13` (T105–T109 tests red phase); `c443e2c` (Phase 4 closure docs) |
| Phase 5: US3 — Reviewer trusts the system (T116–T133) | Locust load (smoke/full/soak), CI workflows (PR + workflow_dispatch + nightly + record-corpus), Trivy + Syft + gitleaks, custom guards, full Terraform module set per ADR-0005, threat model, README polish | **Complete** | `fe9eb41` (impl); `237d122` (closure docs) |
| Phase 6: Polish & closure (T134–T141) | Coverage sweep to 86.24%, ruff + mypy strict clean, dashboard-lag SLO measured, ADR-0002 eval baseline gating note, /docs cross-link, quickstart end-to-end re-run, SPECKIT block verified, production-readiness review | **Complete** | `990b437` |

**Feature 001 closed.** T142 (PII-strip CI gate, SC-007) is intentionally deferred to Phase 7 per the user's instruction (Phase 6 = T134–T141 only).

T036 is intentionally absent (build-tooling gate moved to `scripts/check_runbook_completeness.py` at T113; see `docs/DECISIONS.md`).

## Test bar at Phase 6 closure (feature 001 final)

| Tier | Pass | Fail | Skip | Wall | Δ vs Phase 5 |
|---|---|---|---|---|---|
| Unit | 214 | 0 | 0 | 5 s | +150 (twenty new files for T134) |
| Contract | 41 | 0 | 0 | ~200 s | 0 |
| Integration | 14 | 0 | 0 | ~225 s | 0 |
| Load (smoke, local) | 280 reqs, 0 failures, p50=50ms | 0 | n/a | 60 s | 0 |
| Coverage | **86.24%** | n/a | n/a | n/a | +52.6pp (was 33.65% on Phase 5 baseline) |

Plus every CI guard green locally:
- `scripts/check_no_todo_fixme.py` — Constitution Principle III
- `scripts/check_slm_pinning.py` — Constitution Principle XIV + ADR-0002
- `scripts/check_runbook_completeness.py` — FR-022
- `python -m collectmind.openapi.dump` diff vs `docs/api/openapi.yaml` — T132
- `ruff check` + `ruff format --check` — Constitution Code Quality Standards
- `mypy --strict` — Constitution Code Quality Standards

Zero verification cycles in Phase 6. Two Phase-1 leftovers fixed by T134 work (dashboard provisioner Counter-suffix bug; `check_no_todo_fixme.py` venv exclusion narrow match).

## Stack-up

```bash
# Bring the foundation stack up.
docker compose -f infra/compose/docker-compose.yaml up -d
until curl -fsS http://localhost:8081/ready >/dev/null 2>&1; do sleep 2; done && echo READY
```

Endpoints:
- Orchestration / Query API: <http://localhost:8081>
- Grafana: <http://localhost:3000>
- Prometheus: <http://localhost:9090>
- Alertmanager: <http://localhost:9093>
- Local webhook receiver: <http://localhost:9099>

## Smoke test

See [`specs/001-policy-loop-vertical-slice/quickstart.md`](../specs/001-policy-loop-vertical-slice/quickstart.md). T139 re-run measured 27.32s end-to-end on a warm stack against the SC-008 600s budget.

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

## What is next — Phase 7 (post-feature-001)

Three named Phase 7 follow-ups inherited from Phase 6 closure:

| Item | Reason | Trigger |
|---|---|---|
| **ADR-0002 eval-suite baseline + promotion to Accepted** | Requires a GPU runner; the closure session ran on a workstation without `nvidia-smi`. Per instruction no baseline numbers fabricated. | First successful workflow_dispatch invocation of `.github/workflows/ci-workflow-dispatch.yaml` `eval-suite` job on a `[self-hosted, gpu]` runner. Lands as the follow-up commit `docs: ADR-0002 record eval baseline`. |
| **SC-009 rolling-5-PR wall-clock window** | Needs at least one real PR-tier CI run as input; pre-emptive aggregator is speculative. | First PR-tier `ci.yaml` invocation. Lands as a small `scripts/ci_wall_clock_window.py` follow-up if SC-009 starts trending toward 18 min. |
| **T142 PII-strip CI gate (closes SC-007)** | Excluded from Phase 6 per user's explicit instruction (`/speckit.implement T134-T141`). | Phase 7 work item; the test exists in skeleton via `src/collectmind/observability/logging.py`'s `_pii_processor`; the CI gate at `scripts/check_log_pii.py` lands in the same PR. |

## What is deferred (named gaps; not silent)

| Item | Source | Reason |
|---|---|---|
| **Audit `UNIQUE (correlation_id, kind)` constraint + `ON CONFLICT DO NOTHING`** (Flag 9 from Phase 3 spot-check) | `src/collectmind/registry/audit.py` | Requires a migration + integration retest. Lands as a Phase 7-or-later migration ADR. |
| **Dedicated `error JSONB` column on `audit_events`** to replace the `_extras` hack (Flag 10) | `src/collectmind/registry/audit.py`, migration `008_audit_events.sql` | Same Phase 7-or-later migration ADR as Flag 9. |
| **Per-signal grouping in `BrakeWearHypothesisRule`** (MEDIUM flag from Phase 3 spot-check) | `src/collectmind/feedback/evaluator.py` | Not load-bearing for feature 001; the rule gets reworked in feature 004 / 005. |
| **VLLMClient resource leak + missing OTel trace propagation on httpx** (MEDIUM flags) | `src/collectmind/slm/vllm_client.py` | Lands alongside the GPU-tier integration work in feature 005's full SLM gating. |
| **ECS execution role does NOT have Secrets Manager read** (MEDIUM, Phase 5 spot-check) | `infra/terraform/secrets/main.tf` | Deliberate — least-privilege; the task role fetches secrets at runtime, not at task launch. |
| **`outcome` audit row keyed by deployment_id, not by the inbound correlation_id** (observed during T139 quickstart) | `src/collectmind/feedback/worker.py` | By design — `deployment_targets` has no `correlation_id` column; the outcome audit is keyed by `deployment_id`. If a future feature wants the inbound correlation_id to chain through to outcome, add a column + migration. T060 already asserts the 4-kind chain without `outcome`. |

## Phase 6 spot-check findings (the four files the user named)

| File | Verdict |
|---|---|
| [`docs/runbook/feature-001-readiness-review.md`](runbook/feature-001-readiness-review.md) | PASS — every NON-NEGOTIABLE walked with named artifact, not "the test passes." Three Phase-7 follow-ups documented. |
| [`docs/adr/0002-default-slm-qwen2-5-7b-instruct.md`](adr/0002-default-slm-qwen2-5-7b-instruct.md) | PASS — Status remains `Proposed` with a T137 gating note; baseline numbers NOT fabricated per instruction. |
| Coverage report (`coverage.xml` after Phase 6) | PASS — 86.24% line coverage; Principle IV's 85% non-negotiable floor satisfied. |
| [`specs/001-policy-loop-vertical-slice/quickstart.md`](../specs/001-policy-loop-vertical-slice/quickstart.md) after T139 re-run | PASS — 27.32s end-to-end on a warm Compose stack against the SC-008 600s budget. |

## Commit chain (feature 001)

```
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
