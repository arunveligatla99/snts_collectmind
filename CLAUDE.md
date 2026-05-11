# CollectMind — Claude Code session primer

This file is the entry point for any Claude Code session opened against this repo. Read it first. Read the files at the end before doing any work.

<!-- SPECKIT START -->
The active feature is `001-policy-loop-vertical-slice`. Read its implementation plan for technologies, project structure, runtime commands, and constraints:

- Plan: `specs/001-policy-loop-vertical-slice/plan.md`
- Spec: `specs/001-policy-loop-vertical-slice/spec.md`
- Research notes: `specs/001-policy-loop-vertical-slice/research.md`
- Data model: `specs/001-policy-loop-vertical-slice/data-model.md`
- Contracts: `specs/001-policy-loop-vertical-slice/contracts/`
- Quickstart: `specs/001-policy-loop-vertical-slice/quickstart.md`

The constitution at `.specify/memory/constitution.md` (v1.0.1) is the highest-priority artifact and overrides any plan choice in conflict with it.
<!-- SPECKIT END -->

## Four-file scaffold

| File | Purpose |
|---|---|
| `CLAUDE.md` | This file. Session primer; principles; mandatory pre-read. |
| `docs/PROJECT_STATE.md` | Snapshot: phase completions, commit SHAs, stack-up commands, what is next, what is deferred. |
| `docs/DECISIONS.md` | Append-only dated decision log. Process and pattern decisions outside the ADR cadence. |
| `docs/TASKS.md` → `specs/001-policy-loop-vertical-slice/tasks.md` | Implementation task list with `[X]` and commit SHAs for completed tasks. |

`docs/TASKS.md` is an alias: open `specs/001-policy-loop-vertical-slice/tasks.md`. The alias exists so the four-file scaffold is uniform regardless of which feature is active.

## Architecture Decision Records

ADRs live at `docs/adr/`. Drafting cadence and table of contents at `docs/adr/README.md`. Current state:

| ADR | Title | Status |
|---|---|---|
| ADR-0001 | COVESA VSS v6.0 pin | Accepted |
| ADR-0002 | Default SLM — Qwen2.5-7B-Instruct | **Proposed** (promotes to Accepted once eval-suite baseline is filled; Phase 6 task T137) |
| ADR-0003 | Constrained-decoding library — outlines | Accepted |
| ADR-0004 | Deterministic-fingerprint Policy Generator stub | Accepted |
| ADR-0005 | SLM hosting topology on AWS — ECS-on-EC2 g5/g6 default | Accepted |
| ADR-0006 | Dev-only `DevDefaultPolicyClient` for local-development workflows (no real SLM required) | Accepted |

## Principles (load-bearing; do not relax silently)

- **Production-grade by default.** Every change is held to the same bar as feature 001 closure. No "demo" framing.
- **SLM-first, isolated, swappable model boundary.** Real SLM in CI contract and integration tiers under deterministic decoding. Frontier LLM is opt-in and gated by a constitution-amendment ADR. (Principle XIII.)
- **Deterministic, budgeted model execution in CI.** Real SLM at `temperature=0` + fixed seed in contract and integration. Deterministic substitute (stub or dev_default) in load and soak. Full SLM load and soak gated to `workflow_dispatch` and nightly only. (Principle XIV.)
- **No mocked subsystems where a real one is feasible.** Postgres + TimescaleDB, Redis, Kafka are real. Mocks only at clearly external boundaries (AI Technician, Collector AI) and only behind contract-tested interfaces. (Principle II.)
- **Test-first posture.** Tests are written before or alongside implementation. The red phase is canonical. (Principle IV.)
- **Trust the gate, audit on signal.** Tests, contract checks, schemathesis fuzz, integration runs, and the dashboard are the operational gate. Reading code by itself catches a fraction of what running it catches; the verification cycle (build → up → poll → drill) is where real bugs surface. The four-file spot-check at phase checkpoints is the human-in-the-loop counterpart. (Process pattern; see `docs/DECISIONS.md`.)
- **Audit is a feature, not a log.** Every policy-generation, validation, deployment, outcome, and erasure operation writes an immutable audit row with the FR-017a minimum field set (composite finding key, SLM repo and revision SHA, prompt template version, decoding seed, policy version, deployment ref, outcome ref). (Principle XVII.)

## Operational notes

- **Docker Desktop instability surfaced once during this project.** If the daemon is down at session start (`failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`), the smoke-test path is documented in `specs/001-policy-loop-vertical-slice/quickstart.md`. Restart Docker Desktop and re-run `docker compose -f infra/compose/docker-compose.yaml up -d`.
- **The session that closed Phase 3 used `SLM_PROFILE=dev_default`.** That client is gated by ADR-0006 to local-only environments via `app.py`'s startup guard (`COLLECTMIND_ENV != "local"` refuses it). For PR-tier CI use `SLM_PROFILE=stub`. For workflow-dispatch full-SLM use `SLM_PROFILE=vllm`.
- **Two HIGH code-review flags from Phase 3 are explicitly deferred:** audit `UNIQUE (correlation_id, kind)` constraint, and a dedicated `error JSONB` column on `audit_events`. Both require migrations and a retest cycle and land in a Phase 5-or-later migration ADR. Logged in `docs/DECISIONS.md`.
- **All three Phase 4 MEDIUMs were closed in Phase 5**: `DashboardLagBreach` predicate replaced with an `up == 1` + `scrape_duration_seconds`-based expression; `SoakErrorRateOrMemoryBreach` split into `SoakErrorRateBreach` + `SoakMemoryGrowthBreach` with the memory half also enforced as a post-run gate by `.github/workflows/nightly.yaml`; `alertmanager.yaml` severity tiers standardized to `critical` (SLO breach, pages immediately) vs `page` (warning-tier, suppressed by inhibit rule when a critical for the same tuple fires).
- **One Phase 5 MEDIUM deferred deliberately**: `infra/terraform/secrets/main.tf`'s ECS execution role does NOT have Secrets Manager read. The app fetches secrets at runtime via the task role (least privilege); a future `valueFrom`-style task definition would require a narrow IAM policy attachment + ADR. Documented in `docs/DECISIONS.md`.
- **Phase 4 added Compose services** (`alertmanager` :9093, `local-webhook` :9099). **Phase 5 added** four GitHub Actions workflows (`ci.yaml`, `ci-workflow-dispatch.yaml`, `nightly.yaml`, `record-corpus.yaml`), the full Terraform module set under `infra/terraform/` (networking, compute, data, storage, secrets, observability, eks variant, ci_runner), and four CI guards (`check_no_todo_fixme.py` Phase 1 venv-traversal bug fixed; `check_slm_pinning.py`; `check_secrets.py`; `check_runbook_completeness.py` already in place from Phase 4).

## Mandatory pre-read at session start

Before doing any work, read these files in order. They are small and they are load-bearing:

1. `CLAUDE.md` (this file).
2. `docs/PROJECT_STATE.md` — current phase, commit SHAs, what is next.
3. `docs/DECISIONS.md` — process patterns and dated rationale outside the ADR cadence.
4. `docs/adr/README.md` — ADR index with drafting cadence.
5. `.specify/memory/constitution.md` — the highest-priority artifact.
6. `specs/001-policy-loop-vertical-slice/spec.md` — what feature 001 must do and why.
7. `specs/001-policy-loop-vertical-slice/plan.md` — the technology and structure decisions.
8. `specs/001-policy-loop-vertical-slice/tasks.md` — what is done (`[X]` + commit SHA) and what is next.
