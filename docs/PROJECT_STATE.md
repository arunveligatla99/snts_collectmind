# Project State — CollectMind

**Updated**: 2026-05-10
**Branch**: `001-policy-loop-vertical-slice`
**Constitution**: v1.0.1 at `.specify/memory/constitution.md`

## Phase status

| Phase | Range | Status | Anchor commit |
|---|---|---|---|
| Phase 1: Setup (T001–T019) | Repo scaffolding, tooling, Compose stack | **Complete** | `50ade89` |
| Phase 2: Foundational (T020–T047, gap at T036) | VSS pin, weight manifest, migrations, OAuth2 verifier, OTel, Kafka topics, error model, runbook stubs, contracts mirrored | **Complete** | `50ade89` |
| Phase 3: US1 — Operator end-to-end policy loop (T048–T104) | Tests in red phase, then full US1 implementation | **Complete** | `b9fddc8` (US1 implementation); `9c4bd7d` (T048–T064 tests red phase); `7dd2723` (Phase 3 verification fixes); `d5f4aa5` (ADR-0006 + startup guard + vLLM CI decoding-strict check) |
| Phase 4: US2 — On-call observes pipeline (T105–T115) | Dashboard JSON, alert rules, runbook pages, alert-rule parity gate | Not started |
| Phase 5: US3 — Reviewer trusts the system (T116–T133) | Load tests, CI workflows, IaC, threat model, README polish | Not started |
| Phase 6: Polish (T134–T142) | Coverage sweep, eval baseline, ADR-0002 promotion, PII strip CI gate | Not started |

T036 is intentionally absent (build-tooling gate moved to `scripts/check_runbook_completeness.py` at T113; see `docs/DECISIONS.md`).

## Test bar at Phase 3 closure

| Tier | Pass | Fail | Skip | Wall |
|---|---|---|---|---|
| Unit | 59 | 0 | 0 | 1 s |
| Contract | 36 | 0 | 0 | 270 s |
| Integration | 10 | 0 | 0 | 129 s |

## Stack-up

```bash
# Bring the foundation stack up (Postgres + TimescaleDB, Redis, Kafka, Tempo, Loki, Prometheus, Grafana, mock OAuth2 issuer, orchestration-api).
docker compose -f infra/compose/docker-compose.yaml up -d
# Wait for /ready.
until curl -fsS http://localhost:8081/ready >/dev/null 2>&1; do sleep 2; done && echo READY
```

## Smoke test

```bash
# Mint a JWT from the local mock issuer.
TOKEN=$(curl -sS -X POST http://localhost:8088/token \
  -d 'grant_type=client_credentials&client_id=feature-001-default&client_secret=local-dev-only' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Publish a brake-wear diagnostic finding.
curl -sS -X POST http://localhost:8081/api/v1/findings \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
    "schema_version": "1.0.0",
    "finding_id": "F-smoke-001",
    "anomaly_type": "brake_wear_early_stage",
    "hypothesis_class": "brake_wear",
    "hypothesis_statement": "rotor temperature excursion correlation",
    "candidate_signals": ["Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear"],
    "vehicle_scope": ["VIN-1"],
    "upstream_confidence": 0.78
  }' | python -m json.tool

# Wait briefly (time-acceleration factor in compose is 10000), then query the outcome.
curl -sS -H "Authorization: Bearer $TOKEN" \
  http://localhost:8081/api/v1/findings/F-smoke-001/outcome | python -m json.tool
```

## Run tests

```bash
# Inside a Python 3.11 (or 3.13) venv with dev deps installed.
PYTHONPATH=src pytest tests/unit -q --no-cov
PYTHONPATH=src pytest tests/contract -q --no-cov           # ~270 s (schemathesis fuzzing)
PYTHONPATH=src pytest tests/integration -q --no-cov        # ~130 s (real local stack)
```

For host venv setup the session that closed Phase 3 used `.venv-test` with pinned deps (see `pyproject.toml`'s `[project.optional-dependencies].dev`).

## What is next

**Phase 4 — User Story 2 (P2, T105–T115):** dashboard JSON, Prometheus alert rules per SLO, one runbook page per alert and per failure mode, alert-rule-to-runbook parity check, Alertmanager configuration. Begins at T105 (contract test asserting the auto-provisioned dashboard parses and references only declared metrics).

The exit criteria are documented in `specs/001-policy-loop-vertical-slice/spec.md` US2 acceptance scenarios.

## What is deferred (named gaps; not silent)

| Item | Source | Reason |
|---|---|---|
| **Audit `UNIQUE (correlation_id, kind)` constraint + `ON CONFLICT DO NOTHING`** (Flag 9 from Phase 3 spot-check) | `src/collectmind/registry/audit.py` | Requires a migration + integration retest. Lands as a Phase 4-or-later migration ADR. |
| **Dedicated `error JSONB` column on `audit_events`** to replace the `_extras` hack (Flag 10) | `src/collectmind/registry/audit.py`, migration `008_audit_events.sql` | Requires a migration + retest. Same Phase 4-or-later migration ADR as Flag 9. |
| **T126 CI guard amendment refusing `SLM_PROFILE=dev_default` in any workflow file** | `scripts/check_slm_pinning.py` (planned in Phase 5) | Application-level startup guard already refuses non-local environments per ADR-0006; CI-pipeline-level guard is belt-and-suspenders. Lands during Phase 5 T126 work. |
| **Eval baseline for ADR-0002** (bracketed fields under "Eval-suite baseline (filled after first eval run)") | `docs/adr/0002-default-slm-qwen2-5-7b-instruct.md` | Requires a real-SLM eval run on a GPU runner. Lands at T137 (Phase 6 Polish) via a follow-up commit titled `docs: ADR-0002 record eval baseline`. ADR-0002 promotes from Proposed to Accepted in the same commit. |
| **Per-signal grouping in `BrakeWearHypothesisRule`** (MEDIUM flag from Phase 3 spot-check) | `src/collectmind/feedback/evaluator.py` | Not load-bearing for feature 001; the rule gets reworked in feature 004 (validator hardening) or feature 005 (confidence gating). |
| **VLLMClient resource leak + missing OTel trace propagation on httpx** (MEDIUM flags) | `src/collectmind/slm/vllm_client.py` | Land alongside the GPU-tier integration work in feature 005's full SLM gating. |

## Commit chain (feature 001)

```
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
