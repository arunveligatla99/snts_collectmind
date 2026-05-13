# CollectMind — Claude Code session primer

This file is the entry point for any Claude Code session opened against this repo. Read it first. Read the files at the end before doing any work.

<!-- SPECKIT START -->
**Feature 001 — `policy-loop-vertical-slice` — is shipped** (`990b437` + `a49939e`). Closure artifact at [`docs/runbook/feature-001-readiness-review.md`](docs/runbook/feature-001-readiness-review.md): every NON-NEGOTIABLE constitutional principle (IV, VII, IX, X, XI, XIII, XIV) is PASS with a named artifact.

**Feature 002 — `multi-tenant-isolation` — SHIPPED** (branch `002-multi-tenant-isolation`). All 14 phases closed. Closure artifact at [`docs/runbook/feature-002-readiness-review.md`](docs/runbook/feature-002-readiness-review.md): every NON-NEGOTIABLE constitutional principle PASS with a named artifact; ADR-0007 + ADR-0009 promoted Accepted; ADR-0008 stays Proposed with documented workflow_dispatch SC-002/SC-003 gating note. Phase status table at [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md).

Active feature artifacts (feature 002):

- Plan: `specs/002-multi-tenant-isolation/plan.md`
- Spec: `specs/002-multi-tenant-isolation/spec.md`
- Research notes: `specs/002-multi-tenant-isolation/research.md`
- Data model: `specs/002-multi-tenant-isolation/data-model.md`
- Contracts: `specs/002-multi-tenant-isolation/contracts/` (audit-admin.v1.yaml NEW; orchestration-api + query-api delta files for v1.1.0)
- Quickstart: `specs/002-multi-tenant-isolation/quickstart.md`
- Tasks: `specs/002-multi-tenant-isolation/tasks.md` (T200-T296 closed)
- Readiness review: `docs/runbook/feature-002-readiness-review.md`

Feature 001 artifacts remain load-bearing as the inherited baseline (Spec Dependencies §):

- Plan: `specs/001-policy-loop-vertical-slice/plan.md`
- Spec: `specs/001-policy-loop-vertical-slice/spec.md`
- Readiness review: `docs/runbook/feature-001-readiness-review.md`

Three Phase-7 follow-ups from feature 001 still listed in [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md): ADR-0002 baseline + Accepted promotion (gated to a GPU runner), SC-009 rolling-5-PR wall-clock window logic (gated to the first PR-tier CI run), T142 PII-strip CI gate (closes SC-007). T142 is an upstream dependency of feature-002 SC-007 per Spec Assumptions §8.

The constitution at `.specify/memory/constitution.md` (v1.0.1) is the highest-priority artifact and overrides any plan choice in conflict with it.
<!-- SPECKIT END -->

## Four-file scaffold

| File | Purpose |
|---|---|
| `CLAUDE.md` | This file. Session primer; principles; mandatory pre-read. |
| `docs/PROJECT_STATE.md` | Snapshot: phase completions, commit SHAs, stack-up commands, what is next, what is deferred. |
| `docs/DECISIONS.md` | Append-only dated decision log. Process and pattern decisions outside the ADR cadence. |
| `docs/TASKS.md` → `specs/001-policy-loop-vertical-slice/tasks.md` | Implementation task list with `[X]` and commit SHAs for completed tasks. |

`docs/TASKS.md` is an alias: open `specs/001-policy-loop-vertical-slice/tasks.md`. The alias retargets to `specs/002-…/tasks.md` once feature 002 starts.

## Architecture Decision Records

ADRs live at `docs/adr/`. Drafting cadence and table of contents at `docs/adr/README.md`. Current state:

| ADR | Title | Status |
|---|---|---|
| ADR-0001 | COVESA VSS v6.0 pin | Accepted |
| ADR-0002 | Default SLM — Qwen2.5-7B-Instruct | **Proposed** (T137 gating note recorded; promotes to Accepted once eval-suite baseline is filled on a GPU runner; follow-up commit `docs: ADR-0002 record eval baseline`) |
| ADR-0003 | Constrained-decoding library — outlines | Accepted |
| ADR-0004 | Deterministic-fingerprint Policy Generator stub | Accepted |
| ADR-0005 | SLM hosting topology on AWS — ECS-on-EC2 g5/g6 default | Accepted |
| ADR-0006 | Dev-only `DevDefaultPolicyClient` for local-development workflows (no real SLM required) | Accepted |
| ADR-0007 | Row-Level Security hardening posture + break-glass service-principal bypass | **Accepted** (promoted at Phase 9 closure; integration tier validates RESTRICTIVE+PERMISSIVE-baseline pattern + break-glass atomic audit + SET LOCAL ROLE connection-pool contract per Phase 9.b worked example) |
| ADR-0008 | Per-tenant ingress rate limiting + hot-store key migration mechanism | **Proposed** (Phase 10 + Phase 11 implementation green; Phase 14 T293 cleanup completed the hot-store rollover; promotes to Accepted on the first successful workflow_dispatch SC-002 + SC-003 run against the rate-limited orchestration-api per Principle XIV — same gating pattern as ADR-0002) |
| ADR-0009 | Tenant-Vehicle Ownership store — mutable current row + append-only history | **Accepted** (promoted at Phase 9 closure; tenant_vehicles + tenant_vehicles_history tables in use; history immutability trigger + atomic `kind=vehicle_assignment_change` audit row both verified at integration tier; Phase 12 closure adds the deployer-hot-path validation per Part 6 + the write-through Redis ownership cache per Part 4 with failure-OPEN posture explicitly contrasted with ADR-0008's failure-CLOSED rate-limiter) |

## Principles (load-bearing; do not relax silently)

- **Production-grade by default.** Every change is held to the same bar as feature 001 closure. No "demo" framing.
- **SLM-first, isolated, swappable model boundary.** Real SLM in CI contract and integration tiers under deterministic decoding. Frontier LLM is opt-in and gated by a constitution-amendment ADR. (Principle XIII.)
- **Deterministic, budgeted model execution in CI.** Real SLM at `temperature=0` + fixed seed in contract and integration. Deterministic substitute (stub or dev_default) in load and soak. Full SLM load and soak gated to `workflow_dispatch` and nightly only. (Principle XIV.)
- **No mocked subsystems where a real one is feasible.** Postgres + TimescaleDB, Redis, Kafka are real. Mocks only at clearly external boundaries (AI Technician, Collector AI) and only behind contract-tested interfaces. (Principle II.)
- **Test-first posture.** Tests are written before or alongside implementation. The red phase is canonical. (Principle IV.)
- **Trust the gate, audit on signal.** Tests, contract checks, schemathesis fuzz, integration runs, and the dashboard are the operational gate. Reading code by itself catches a fraction of what running it catches; the verification cycle (build → up → poll → drill) is where real bugs surface. The four-file spot-check at phase checkpoints is the human-in-the-loop counterpart. (Process pattern; see `docs/DECISIONS.md`.)
- **Audit is a feature, not a log.** Every policy-generation, validation, deployment, outcome, and erasure operation writes an immutable audit row with the FR-017a minimum field set (composite finding key, SLM repo and revision SHA, prompt template version, decoding seed, policy version, deployment ref, outcome ref). (Principle XVII.)
- **No fabrication on measurements.** Numbers in ADRs, runbooks, and readiness reviews are recorded from real runs or marked gating-bracketed. ADR-0002's eval-suite baseline rows remain bracketed until a GPU runner produces them (T137 closure-session disposition).

## Operational notes

- **Docker Desktop instability surfaced once during this project.** If the daemon is down at session start (`failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`), the smoke-test path is documented in `specs/001-policy-loop-vertical-slice/quickstart.md`. Restart Docker Desktop and re-run `docker compose -f infra/compose/docker-compose.yaml up -d`.
- **`SLM_PROFILE` selection**: foundation smoke and dev quickstart use `dev_default` (gated by `app.py` startup guard to `COLLECTMIND_ENV=local` per ADR-0006). PR-tier CI uses `stub` (deterministic-fingerprint stub per ADR-0004). Workflow-dispatch + nightly use `vllm` (real SLM). The `scripts/check_slm_pinning.py` guard refuses any workflow file that sets `dev_default`.
- **Repo rename: `collectmind` → `snts_collectmind` (2026-05-13)**. The old `arunveligatla99/collectmind` remote carried an unrelated "day-1 … day-7" scratch history with no merge-base against the CollectMind constitution lineage; `gh pr create` refused cross-tree PRs. The CollectMind track moved to `github.com/arunveligatla99/snts_collectmind` (empty at rename time; no legacy collisions). Local `master` (pre-feature-001 scaffold) pushed as the new `main`; `001-policy-loop-vertical-slice` + `002-multi-tenant-isolation` pushed as feature branches; `arun/develop` is the reconciliation branch (feature 002 + PR #1's 13 CI fixes merged on top of new main; carries PR #2). Run `git remote set-url origin https://github.com/arunveligatla99/snts_collectmind.git` if cloning fresh from a local copy that still tracks the old URL. Full rationale in `docs/DECISIONS.md` (2026-05-13 entry).
- **Two HIGH code-review flags from Phase 3 are explicitly deferred** to a Phase 7-or-later migration ADR: audit `UNIQUE (correlation_id, kind)` constraint, and a dedicated `error JSONB` column on `audit_events`. Both require migrations and an integration retest. Logged in `docs/DECISIONS.md`.
- **All three Phase 4 MEDIUMs were closed in Phase 5**: `DashboardLagBreach` predicate replaced with an `up == 1` + `scrape_duration_seconds`-based expression; `SoakErrorRateOrMemoryBreach` split into `SoakErrorRateBreach` + `SoakMemoryGrowthBreach` with the memory half enforced as a post-run gate by `.github/workflows/nightly.yaml`; `alertmanager.yaml` severity tiers standardized to `critical` vs `page`.
- **One Phase 5 MEDIUM deferred deliberately**: `infra/terraform/secrets/main.tf`'s ECS execution role does NOT have Secrets Manager read. The app fetches secrets at runtime via the task role (least privilege). Documented in `docs/DECISIONS.md`.
- **Phase 6 closure (feature 001 done at `990b437` + `a49939e`)**: coverage **86.24%** across **214 unit + 41 contract + 14 integration** tests; `ruff check` + `ruff format --check` + `mypy --strict` all clean; every CI guard (`check_no_todo_fixme`, `check_slm_pinning`, `check_runbook_completeness`, OpenAPI dump diff) green locally. Production-readiness review at [`docs/runbook/feature-001-readiness-review.md`](docs/runbook/feature-001-readiness-review.md) walks every NON-NEGOTIABLE with a named artifact.
- **Two latent Phase-1 bugs fixed in Phase 6** while writing coverage tests: `observability/dashboard_provisioner.py`'s `declared_metric_names()` now honors `prometheus_client` Counter `_total` suffix stripping (the T105 dashboard contract test had the same fix in Phase 4 — the provisioner module shipped the buggy version until now); `scripts/check_no_todo_fixme.py` excludes `.venv*` (was only excluding the bare `.venv` path component).

## Mandatory pre-read at session start

Before doing any work, read these files in order. They are small and they are load-bearing:

1. `CLAUDE.md` (this file).
2. `docs/PROJECT_STATE.md` — current phase, commit SHAs, what is next, deferred items, Phase-7 follow-ups.
3. `docs/runbook/feature-001-readiness-review.md` — **feature 001 closure artifact**. Every NON-NEGOTIABLE constitutional principle PASS with a named artifact. Read before treating any closed item as "shipped."
4. `docs/DECISIONS.md` — process patterns and dated rationale outside the ADR cadence.
5. `docs/adr/README.md` — ADR index with drafting cadence.
6. `.specify/memory/constitution.md` — the highest-priority artifact.
7. `specs/001-policy-loop-vertical-slice/spec.md` — what feature 001 must do and why.
8. `specs/001-policy-loop-vertical-slice/plan.md` — the technology and structure decisions.
9. `specs/001-policy-loop-vertical-slice/tasks.md` — what is done (`[X]` + commit SHA). Every Phase-6 task is closed; the file is now a historical record.

When feature 002 begins (`/speckit-specify 002-multi-tenant-isolation`), the spec / plan / tasks links above retarget to the `002-…` directory and a new spec-kit phase chain begins. The four-file scaffold and pre-read posture do not change.
