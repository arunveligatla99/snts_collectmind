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
| Phase 5: US3 — Reviewer trusts the system (T116–T133) | Locust load (smoke/full/soak), CI workflows (PR + workflow_dispatch + nightly + record-corpus), Trivy + Syft + gitleaks, custom guards (no-TODO, SLM pinning, secrets, runbook parity, OpenAPI dump), full Terraform module set per ADR-0005, threat model, README polish | **Complete** | `fe9eb41` |
| Phase 6: Polish (T134–T142) | Coverage sweep, eval baseline, ADR-0002 promotion, PII strip CI gate | Not started |

T036 is intentionally absent (build-tooling gate moved to `scripts/check_runbook_completeness.py` at T113; see `docs/DECISIONS.md`).

## Test bar at Phase 5 closure

| Tier | Pass | Fail | Skip | Wall | Δ vs Phase 4 |
|---|---|---|---|---|---|
| Unit | 64 | 0 | 0 | 1 s | 0 |
| Contract | 41 | 0 | 0 | 202 s | 0 |
| Integration | 14 | 0 | 0 | 225 s | 0 |
| Load (smoke, local) | n/a | 0 errors | n/a | 60 s | new |

Plus four CI guards green locally:
- `scripts/check_no_todo_fixme.py` — Constitution Principle III
- `scripts/check_slm_pinning.py` — Constitution Principle XIV + ADR-0002
- `scripts/check_runbook_completeness.py` — FR-022
- `python -m collectmind.openapi.dump` diff vs `docs/api/openapi.yaml` — T132

Zero verification cycles. One in-flight Phase 1 leftover fixed: `scripts/check_no_todo_fixme.py`'s `.venv` exclude only matched the bare directory name, missing `.venv-test` and similar host-venv layouts. The Phase 5 rewrite uses prefix + regex matching to cover every `.?venv*` form.

## Stack-up

```bash
# Bring the foundation stack up (Postgres + TimescaleDB, Redis, Kafka, Tempo, Loki, Prometheus, Alertmanager, local-webhook receiver, Grafana, mock OAuth2 issuer, orchestration-api).
docker compose -f infra/compose/docker-compose.yaml up -d
# Wait for /ready.
until curl -fsS http://localhost:8081/ready >/dev/null 2>&1; do sleep 2; done && echo READY
```

Endpoints:
- Orchestration / Query API: <http://localhost:8081>
- Grafana (CollectMind End-to-End dashboard auto-provisioned): <http://localhost:3000>
- Prometheus: <http://localhost:9090>
- Alertmanager: <http://localhost:9093>
- Local webhook receiver: <http://localhost:9099>  (GET `/healthz`, GET/DELETE `/captured`)

## Smoke test

See `docs/PROJECT_STATE.md` history for the Phase 3/4 step-by-step. Phase 5 adds the OpenAPI dump check and the load-smoke local-run:

```bash
# OpenAPI dump must match the committed contract.
PYTHONPATH=src python -m collectmind.openapi.dump | diff -u docs/api/openapi.yaml -

# Local smoke load (deterministic stub; 60s, 50 users).
PYTHONPATH=. locust -f tests/load/locustfile_smoke.py \
  --headless --users 50 --spawn-rate 10 --run-time 60s \
  --host http://localhost:8081 --csv reports/smoke
```

## Run tests

```bash
# Inside a Python 3.11 (or 3.13) venv with dev deps installed.
PYTHONPATH=src pytest tests/unit -q --no-cov                # 64 tests, ~1 s
PYTHONPATH=src pytest tests/contract -q --no-cov            # 41 tests, ~200 s
PYTHONPATH=src pytest tests/integration -q --no-cov         # 14 tests, ~225 s
python scripts/check_runbook_completeness.py                # T113 CI guard
python scripts/check_no_todo_fixme.py                       # T125 CI guard
python scripts/check_slm_pinning.py                         # T126 CI guard
python scripts/check_secrets.py                             # T127 (needs gitleaks on PATH)
```

## What is next

**Phase 6 — Polish (T134–T142):** Coverage sweep to bring every module to 85 percent line floor; lint and type sweep; dashboard-lag SLO measurement on steady-state local stack; `make eval` real-SLM run + ADR-0002 baseline-row commit promoting it from Proposed to Accepted; cross-link spec/plan/research/data-model/contracts/quickstart from README; CLAUDE.md SPECKIT-block verification; production-readiness review against every NON-NEGOTIABLE principle; PII-strip CI gate at T142 (closes SC-007).

## What is deferred (named gaps; not silent)

| Item | Source | Reason |
|---|---|---|
| **Audit `UNIQUE (correlation_id, kind)` constraint + `ON CONFLICT DO NOTHING`** (Flag 9 from Phase 3 spot-check) | `src/collectmind/registry/audit.py` | Requires a migration + integration retest. Lands as a Phase 6-or-later migration ADR. |
| **Dedicated `error JSONB` column on `audit_events`** to replace the `_extras` hack (Flag 10) | `src/collectmind/registry/audit.py`, migration `008_audit_events.sql` | Requires a migration + retest. Same Phase 6-or-later migration ADR as Flag 9. |
| **Eval baseline for ADR-0002** (bracketed fields under "Eval-suite baseline (filled after first eval run)") | `docs/adr/0002-default-slm-qwen2-5-7b-instruct.md` | Requires a real-SLM eval run on a GPU runner. Lands at T137 (Phase 6 Polish) via a follow-up commit titled `docs: ADR-0002 record eval baseline`. ADR-0002 promotes from Proposed to Accepted in the same commit. |
| **Per-signal grouping in `BrakeWearHypothesisRule`** (MEDIUM flag from Phase 3 spot-check) | `src/collectmind/feedback/evaluator.py` | Not load-bearing for feature 001; the rule gets reworked in feature 004 (validator hardening) or feature 005 (confidence gating). |
| **VLLMClient resource leak + missing OTel trace propagation on httpx** (MEDIUM flags) | `src/collectmind/slm/vllm_client.py` | Land alongside the GPU-tier integration work in feature 005's full SLM gating. |
| **ECS execution role does NOT have Secrets Manager read** (MEDIUM, Phase 5 spot-check) | `infra/terraform/secrets/main.tf` | Deliberate — the task role fetches secrets at runtime, not at task launch (least privilege). If a future container needs `valueFrom: secretsmanager`-shaped secrets at launch, add the grant explicitly via a new IAM policy attachment alongside an ADR. Documented in `docs/DECISIONS.md`. |
| **Phase 1 leftover: container OOM ADR / actually closed** | resolved | Phase 5 `scripts/check_no_todo_fixme.py` rewrite fixed the venv-traversal bug; the Phase 1 script was correct policy with a layout gap. |
| **`ci.yaml` rolling 5-PR wall-clock window** (T119 follow-up) | `.github/workflows/ci.yaml` `wall-clock` job | Currently emits `ci-wall-clock.json` as an artifact but does not yet read prior PR values to enforce the rolling window. Lands as a small Phase 6 follow-up script `scripts/ci_wall_clock_window.py` if SC-009 starts trending toward 18 minutes. |

## Phase 5 spot-check findings

Files reviewed: `.github/workflows/ci.yaml`, `infra/terraform/compute/main.tf`, `docs/security/threat-model.md`, `infra/terraform/secrets/main.tf`.

Zero HIGH. Three MEDIUMs:
1. **Fixed inline**: `pip-audit --ignore-vuln GHSA-0000-0000-0000` placeholder removed (misleading; implied a known-ignored CVE).
2. **Fixed inline**: `contract-tests` step comment clarified — runs under `SLM_PROFILE=stub`; FR-022's real-SLM 60s-warm-path contract is workflow_dispatch-tier.
3. **Deferred** (documented in `docs/DECISIONS.md` + above): ECS execution role does NOT have Secrets Manager read. Least-privilege choice — the task role fetches secrets at runtime, not at task launch.

Several LOW (cosmetic) deferred to Phase 6 polish sweep: `containerInsights` enabled on both ECS clusters (cost ≠ correctness); terraform plan `\|\| true` swallows credentials-missing errors in PR-tier (intentional; documented inline).

## Commit chain (feature 001)

```
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
