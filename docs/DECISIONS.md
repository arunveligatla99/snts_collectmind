# Decisions Log — CollectMind

Append-only, dated. Process and pattern decisions outside the ADR cadence. ADRs cover architectural and supply-chain decisions; this file covers everything else (review patterns, deferral rationales, gap conventions, worked examples).

Entries are sorted oldest-first. New entries append at the bottom.

---

## 2026-05-09 — SC-009 PR-tier vs `workflow_dispatch`-tier split

**Decision**: SC-009's 20-minute wall-clock budget applies to the PR-tier CI pipeline only. Workflow-dispatch tiers (full SLM eval, full-profile load, soak) are not measured by SC-009. SC-002 (1,000 events/s/tenant for 30 min) and SC-003 (24-hour soak) run only on `workflow_dispatch` and on the scheduled cadence recorded in the runbook.

**Source**: Spec Clarifications Q4 + SC-002 / SC-003 / SC-009 wording in `specs/001-policy-loop-vertical-slice/spec.md`. Anchors a binding cost-discipline rule (Constitution Principle XIV).

**Why this matters**: Without the split, the test bar is either too lax (everything skips on PR) or too strict (full SLM load on every PR). The split is the operational expression of Principle XIV's "deterministic substitute for load, real SLM in contract and integration."

---

## 2026-05-09 — FR-017a drilldown in T060 (audit-record minimum field set)

**Decision**: The end-to-end integration test (T060, `tests/integration/test_e2e_finding_to_outcome.py::test_finding_to_outcome_end_to_end`) drills into the `generated` audit event and asserts FR-017a's minimum field set: `slm_repo`, `slm_revision_sha` (40 chars), `prompt_template_version` (non-empty), `slm_decoding_seed` (int), `policy_ref` (non-null with composite key shape), and the corresponding `deployed` event's `deployment_ref` (non-null with `deployment_id`).

**Why this matters**: The audit-record minimum field set is the operational vehicle for FR-017a, and Constitution Principle XVII frames audit as "a feature, not a log." If T060 only asserted the happy-path data flow without drilling into audit, FR-017a would be untested at the integration tier and silent regressions would survive into production. The drilldown raises the cost of forgetting to populate the audit fields to "the e2e test fails," which is the right cost.

---

## 2026-05-09 — `BrakeWearHypothesisRule` inclusive-on-confirm at threshold (T056)

**Decision**: `BrakeWearHypothesisRule.evaluate` uses `value >= expected_threshold` (inclusive on confirm). At value equal to threshold, the rule confirms. T056's parametrized test pins the inclusive-on-confirm semantics at `threshold ∈ {0.0, 0.5, 1.0}`.

**Why this matters**: Tie semantics at the threshold boundary are a real source of silent disagreement between the test and the implementation. The original T056 assertion was tautological (`outcome in {confirmed, ruled_out, no_data}`), which would pass with any rule. The user's spot-check at the Phase 3 test-design checkpoint caught this and replaced it with a specific pin. Records the inclusive-on-confirm choice so future rule rework (feature 004 / feature 005) inherits the same semantics.

---

## 2026-05-09 — Numbering gap at T036 (convention)

**Decision**: Task IDs in `specs/001-policy-loop-vertical-slice/tasks.md` are stable. T036 was dropped (a `runbook_check.py` build-tooling module duplicated T113's script-level gate); the gap at T036 is intentional. Subsequent task IDs (T037 onward) keep their numbering rather than renumber.

**Why this matters**: Renumbering 100+ tasks to close one gap is high-risk, low-value churn. The convention is: drop tasks by removing the line, leave the ID gap, and note the gap in `tasks.md` itself and in `CLAUDE.md`. Future feature task lists follow the same rule.

---

## 2026-05-09 — Four-files spot-check pattern at phase checkpoints

**Decision**: At every phase checkpoint, the human reviewer (user) names a small set of files (3–6) to spot-check end-to-end, plus an automated gate (test pass/fail per tier). The reviewer trusts the gate for everything outside the named files. Findings are reported with severity (LOW / MEDIUM / HIGH) and either fixed inline (when low-cost) or deferred to a named follow-up.

**Worked example**: Phase 3 closure spot-checked `graph/build.py`, `slm/vllm_client.py`, `registry/audit.py`, `feedback/evaluator.py`. Caught one HIGH (`vllm_client.py` temperature-zero refusal slipping at temp=0.0001 due to int truncation), two HIGH deferred (`audit.py` idempotency + error-column), several MEDIUMs and LOWs. The HIGH-deferred items landed on `PROJECT_STATE.md` deferred list. The HIGH-fix landed in `d5f4aa5`.

**Why this matters**: Reading the entire codebase at every checkpoint is impossible and noisy. Naming 3–6 files keeps the human review proportional to the change, and the test gate covers the rest. The pattern works because the file selection targets the load-bearing modules per phase (in Phase 3 closure: graph composition, real SLM client, audit writer, feedback rule).

---

## 2026-05-09 — Test-first stop-at-T064 review pattern

**Decision**: User reviewed all 17 US1 test files (T048–T064) end-to-end before any implementation began (T065+). The test files were committed in the red phase (canonical TDD); implementation followed only after the test design was approved.

**Why this matters**: Tests express the contract that the implementation must satisfy. Reviewing tests-only (without implementation in scope) means the reviewer is reasoning about the contract, not the code. The pattern surfaces test-design defects (e.g., the tautological inclusive-on-confirm assertion in T056) before any implementation locks in a wrong shape. Principle IV's "tests are written before or alongside implementation, never after the fact" is the constitutional anchor.

---

## 2026-05-09 — Trust-the-gate, audit-on-signal review posture

**Decision**: The phase-closure review is a two-pillar process. Pillar one: the automated gate (unit / contract / integration pass per tier, plus dashboards, alerts, and CI checks). Pillar two: the four-files spot-check by a human reviewer on the load-bearing modules. Outside those two pillars, the reviewer does not re-read the code. If a regression slips past both pillars, the response is to add a test or a check, not to expand the spot-check to every file.

**Worked example, Phase 3 closure**: 13 verification fix-and-retest cycles took the integration tier from "code committed" to "10/10 passing." Each cycle surfaced a real bug:
1. Schemathesis 3.x/4.x API rename (`from_path` → `openapi.from_path` and different `base_url` semantics).
2. `force_schema_version="30"` needed for OpenAPI 3.1 sources under schemathesis 3.x.
3. Server-URL prefix `/api/v1` not stripped by `base_url` override; full path mismatch.
4. `/health` and `/ready` declared under server `/api/v1` in the contract; aliases added at `/api/v1/health` and `/api/v1/ready`.
5. Python `\d+` matches Unicode digits; schemathesis fuzz `"1.0.᭖"` slipped past the SemVer check and caused 500 on `int(...)`. Tightened regex to `[0-9]+`.
6. Schemathesis `%00`-byte fuzz on path parameters caused asyncpg 500. Added `_ensure_safe` path-parameter validator returning `NOT_FOUND` on non-printable input.
7. `pyproject.toml` missing the `integration` pytest marker under `--strict-markers`.
8. `require_slm()` gating prevented integration tests from running under the dev_default profile. Stripped from integration tier; dev_default exercises the LangGraph in-process.
9. Default brake-wear VSS names (`Vehicle.Chassis.Brake.PadWear`, `EngineOilTemperature`) do not exist in VSS v6.0. Replaced with real leaf names (`Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear`, `Vehicle.Powertrain.CombustionEngine.EngineOil.Temperature`).
10. `TIME_ACCELERATION_FACTOR=1.0` in compose env meant the 72-hour logical collection window required 72 wall-hours. Set to `10000.0` so it completes in 26 s.
11. The 60-second test polling deadline for outcomes was margin-tight; the higher acceleration factor gives the feedback worker headroom.
12. Telemetry from prior deployments leaked into outcomes for new deployments on the same `VIN-1`. Feedback worker now filters telemetry by `policy_ref @> {policy_id, version}`.
13. `T060` asserted `slm_repo == "Qwen/Qwen2.5-7B-Instruct"` but the foundation smoke runs `dev_default` which reports `slm_repo == "dev/default"`. Relaxed the assertion to `in {Qwen, dev/default}` and documented the deviation in the test docstring + `ADR-0006`.

**Why this matters**: None of those 13 bugs would have been caught by reading the code. All of them surfaced by running it. The verification cycle (build → up → poll → drill into DB) is where real bugs surface. The pattern justifies the cost of building real local stacks and running them on every PR; it is also the operational anchor for Principle II (no mocked subsystems where a real one is feasible).

---

## 2026-05-09 — `DevDefaultPolicyClient` as a fourth dev-only `PolicyGeneratorClient`

**Decision**: A fourth `PolicyGeneratorClient` implementation, `DevDefaultPolicyClient`, exists at `src/collectmind/slm/dev_default_client.py`. Gated to local-only environments by a startup guard in `app.py` (`COLLECTMIND_ENV != "local"` refuses the client). Documented in `docs/adr/0006-dev-default-policy-client.md`. Cross-referenced from `specs/001-policy-loop-vertical-slice/spec.md` Assumptions.

**Why this matters**: Without it, the foundation quickstart (Spec SC-008) cannot complete the end-to-end loop on a clean clone in under 10 minutes; the deterministic-fingerprint stub raises `MissingFingerprint` on every unique inbound finding, and the real SLM clients require a 14 GB GPU-only weight pull. The deviation from Principle XIII's "structured output MUST be schema-constrained at decode time" is real and is bounded by the startup guard plus the planned T126 CI guard amendment. ADR-0006 records the deviation rather than papering over it.

---

## 2026-05-09 — Audit-table improvements deferred to a Phase 4-or-later migration ADR (Flag 9 + Flag 10)

**Decision**: Two HIGH-severity findings from the Phase 3 spot-check are deferred:

- **Flag 9**: `audit_events` has no `UNIQUE (correlation_id, kind)` constraint and the writer mints fresh `event_id` ULIDs on every call. A retried writer (or a future Kafka-consumer rewrite) produces duplicate audit rows.
- **Flag 10**: The audit writer stuffs error payloads into `originating_finding._extras.error` because the table has no `error` column. The runner unwraps it in `_row_to_event`. The hack works but abuses a typed business field for transport.

Both require a migration (a new SQL file in `src/collectmind/registry/migrations/sql/`) plus an integration retest cycle. They land in a Phase 4-or-later migration ADR.

**Why this matters**: Phase 3 closure is not blocked by either issue (the audit chain produces correct rows on the happy path, and the `_extras` hack is recoverable on read). Bundling them with the migration that adds an `error` column is cheaper than two separate migrations. Logged here so they are not silent and a future session does not stumble on the duplicate-audit-row scenario without context.

---

## 2026-05-11 — Phase 4 closure: zero verification cycles, three MEDIUM spot-check deferrals

**Decision**: Phase 4 (US2, T105–T115) closed with zero verification fix-and-retest cycles. The test bar — 64 unit, 41 contract, 14 integration — went green on the first run against the real local Compose stack. Three MEDIUM-severity issues surfaced in the four-files spot-check at closure (rules.yaml `DashboardLagBreach` idle false-positive; `SoakErrorRateOrMemoryBreach` title-vs-expression mismatch; `alertmanager.yaml` inhibit rule referencing an unused `severity="critical"` tier). All three are documented on `docs/PROJECT_STATE.md`'s deferred list and land during Phase 5 (T120/T121 workflow_dispatch + nightly workflows, severity-tier standardization) rather than blocking Phase 4 closure.

**Why this matters**: The zero-cycle closure is a real datapoint, not a sign the test bar is too lax. The deferred set names exactly what would have surfaced if the test bar covered idle-state behavior and severity-tier semantics — both of which the Phase 4 tests deliberately do not cover (T105 asserts dashboard structure, T106 asserts alert/runbook parity, T107 asserts webhook routing, T108 asserts dashboard data-freshness under load, T109 asserts recovery from a real outage). Each of the three deferred items needs a new test or a new check to lock the fix in; that test or check is what the Phase 5 work item produces alongside the fix. This is the canonical "trust the gate, audit on signal, defer on signal" pattern at work, contrasted with Phase 3's 13-cycle close where the bugs were in the load-bearing path and had to land inline.

**Worked example**: `DashboardLagBreach` uses `time() - max(timestamp(collectmind_diagnostic_findings_received_total))`. Under steady load the expression measures Prometheus scrape lag, which is what SC-006 cares about. Under idle (no findings ever published in the session window) the counter has no recent sample, so `timestamp(...)` returns the last evaluation time and the lag appears infinite. The local Compose smoke runs under idle by default, which is why the issue surfaced in the spot-check, not in T108 (which publishes a finding before asserting). The fix replaces the predicate with `up{job="orchestration-api"} == 1` and `(time() - prometheus_target_last_scrape_seconds_ago)` for the freshness signal. The replacement lands in Phase 5 with a new unit test that drives the rules.yaml expression through Prometheus's promtool unit-test runner.

## 2026-05-11 — T106 + T113 enforce the same canonical runbook section set, with `Related ADRs` / `Related FRs` non-enforced

**Decision**: Both `tests/unit/test_alert_runbook_parity.py` (T106) and `scripts/check_runbook_completeness.py` (T113) enforce exactly four canonical runbook sections per alert page: `Symptoms`, `Dashboard`, `Mitigation`, `Escalation`. `Related ADRs` and `Related FRs` are present on every Phase 4 page but are NOT CI-enforced. The matching regex is `^#+\s*<Section>\b` so the heading level (h2, h3, etc.) is free and the section name is matched as a word.

**Why this matters**: T106 and T113 are two views of the same contract — the test surface and the CI surface. If they disagree, a PR can pass pytest and fail CI (or vice versa) and the developer experience degrades. By writing the section list once and using it on both sides, the contract is single-sourced. Not enforcing `Related ADRs` / `Related FRs` keeps a future alert from being blocked because no ADR cross-reference applies — a real situation (e.g., the query latency alert has no ADR motivation). The section set deliberately matches the heading text exactly as written in T112's pages, so future authors do not need to guess between "Symptoms" and "Symptoms Observed."

## 2026-05-11 — `policy_outcome_total` is a single counter with a `state` label, not three counters

**Decision**: The Phase 4 dashboard's generation funnel renders `confirmed`, `ruled_out`, and `no_data` outcome rates as series under one PromQL expression: `sum by (state) (rate(collectmind_policy_outcome_total[1m]))`. The metric is declared once with `labelnames=("tenant_id", "state")`. The hypothesis confirmation rate panel filters `state="confirmed"` against the same counter.

**Why this matters**: An earlier draft of the dashboard JSON referenced three counter names (`policy_outcome_confirmed_total`, `..._ruled_out_total`, `..._no_data_total`) that do not exist in `metrics.py`. The label-on-one-counter design is more idiomatic Prometheus and lets the dashboard render any new outcome state (e.g., `evidence_insufficient` in feature 004) without a new metric registration. T105's bidirectional declared-metric check caught this drift during the red phase before the dashboard was rewritten.

## 2026-05-11 — Phase 6 closure: feature 001 is shipped; three named Phase-7 follow-ups

**Decision**: Phase 6 (T134–T141) closed with all seven NON-NEGOTIABLE constitutional principles PASS against named artifacts in `docs/runbook/feature-001-readiness-review.md`. Test bar at closure: 214 unit, 41 contract, 14 integration tests passing; line coverage 86.24% (over the 85% Principle IV floor); ruff check + ruff format --check + mypy --strict all clean; every CI guard green locally. Three Phase-7 follow-ups are explicitly named and inherit from real blockers (GPU runner availability for ADR-0002 baseline; first PR-tier CI run for SC-009 rolling-window; T142 PII-strip CI gate excluded from Phase 6 per the user's explicit task-set instruction).

**Why this matters**: The closure document is the contract for what "feature 001 is shipped" means. Each NON-NEGOTIABLE is anchored to a specific artifact, test, or check — not to a vague "the test passes." The three follow-ups are tied to specific triggers (GPU runner, first CI run, separate task) rather than being open-ended. A future reviewer can verify the closure independently from this commit + the readiness-review document.

## 2026-05-11 — Phase 6 closure: coverage from 33.65% to 86.24% by mocking, not by lowering the floor

**Decision**: Phase 6 T134 brought coverage over the 85% Principle IV floor by writing twenty new test files that target pure-Python modules and HTTP routers via FastAPI TestClient + dependency-injection mocks (asyncpg, redis-py, aiokafka, httpx via respx). The 85% floor was NOT lowered or carved out by per-module exclusion; the entire `src/collectmind/` tree is measured.

**Why this matters**: The constitution's Principle IV says "85 percent line coverage on application code, measured by pytest-cov, enforced in CI." Two paths could have closed the gap: (a) refactor integration tests to run in-process via TestClient so they contribute to coverage, or (b) write unit tests with mocks. Path (a) breaks Principle II ("no mocked subsystems where a real one is feasible") because the integration tests deliberately exercise the real local stack via HTTP. Path (b) keeps Principle II intact AND honors Principle IV by adding *unit* tests for the in-process paths the integration tier covers via HTTP. The right answer was (b); the test pyramid widens at the unit tier and stays narrow at the integration tier, which is the standard shape.

## 2026-05-11 — Phase 6 closure: two latent Phase-1 bugs surfaced by the coverage work

**Decision**: T134 surfaced two latent bugs that the existing test bar didn't catch:

1. `observability/dashboard_provisioner.py`'s `declared_metric_names()` didn't honor `prometheus_client.Counter`'s `_total` suffix stripping. The Phase 4 T105 dashboard contract test had the SAME bug and fixed it inline (the test file did its own metric-name normalization). The provisioner module shipped the buggy version until Phase 6; the new `tests/unit/test_dashboard_provisioner.py` surfaces it via a real dashboard validation.
2. `scripts/check_no_todo_fixme.py` excluded `.venv` only as a bare path component (`if part == ".venv"`). The local virtualenv lives at `.venv-test`, which never matched. The first standalone invocation of the script (in Phase 6 sanity-checking) found 17 TODO markers — all inside `.venv-test`'s third-party packages. Phase 6 rewrote the exclusion to match the `.?venv*` prefix family and added a per-file exclude for `.pre-commit-config.yaml` (legitimately names the hook id `no-todo-fixme`).

**Why this matters**: Both bugs are perfect examples of why coverage matters as a forcing function, not just as a number. The dashboard provisioner module had 0% coverage before Phase 6 — it shipped buggy and nobody knew because nothing exercised it. Writing the test surfaced the bug. The Phase 6 closure document calls these out explicitly so future reviewers can see that the coverage work is not just box-ticking.

## 2026-05-11 — Phase 5 closure: T128 ECS execution role intentionally does NOT have Secrets Manager read

**Decision**: `infra/terraform/secrets/main.tf` grants `secretsmanager:GetSecretValue` to the orchestration-api task role only, not to the ECS execution role. The task definition does NOT use `valueFrom: secretsmanager` shapes; the application code fetches secrets at runtime via the AWS SDK using the task role's credentials.

**Why this matters**: ECS task definitions support two paths for secrets: (a) ECS fetches at task launch via the execution role and injects as env vars; (b) the application fetches at runtime via the task role. Path (a) is convenient and works well when secrets are stable; path (b) is the least-privilege choice — the execution role stays scoped to ECR pulls and CloudWatch logs only, and the application can re-fetch secrets on rotation without restarting the task. The Phase 5 spot-check on `secrets/main.tf` flagged this as MEDIUM because the execution role lacked the grant; the decision here is that the absence is deliberate. If a future container genuinely needs `valueFrom`-shape secrets, the right move is a new IAM policy attachment scoped narrowly, recorded alongside an ADR — not a blanket execution-role grant.

## 2026-05-11 — Phase 5 closure: zero verification cycles, three MEDIUM spot-check findings (two fixed inline)

**Decision**: Phase 5 (US3, T116–T133) closed with zero verification fix-and-retest cycles. Test bar held at 64 unit / 41 contract / 14 integration (no regression from Phase 4) plus the local smoke load (60 s, 50 users, deterministic stub, 0 failures, p50 = 50 ms). Three MEDIUM-severity issues surfaced in the four-files spot-check at closure; two were fixed inline and one (the ECS-execution-role choice above) was documented as deliberate.

**Why this matters**: This is the second Phase in a row to close zero-cycle. The pattern repeats: tests in red phase, implementation, verification against the real local stack, then a four-files spot-check that catches what the test bar deliberately does not. Phase 5 is the broader of the two closures (32 files, 2729 insertions vs Phase 4's 33 files / 1238 insertions) because IaC + CI workflows + threat model are wide-but-shallow. The pattern works for wide-but-shallow as well as deep-and-narrow.

## 2026-05-11 — Phase 5 closure: severity-tier standardization in `observability/prometheus/rules.yaml`

**Decision**: Phase 5 standardizes alert severity tiers to two values: `severity: critical` (SLO breach, pages immediately) and `severity: page` (warning-tier, paged with longer Alertmanager `group_wait`, suppressed by an inhibit rule when a critical alert for the same `(alertname, service)` is firing). All Phase 5 alerts use `critical` because each measures a binding SLO. `alertmanager.yaml` is updated to match: the inhibit rule now references real-tier names rather than the unused `severity="critical"`-vs-`severity="page"` pair from Phase 4.

**Why this matters**: Phase 4 used `severity: page` for everything and had a dead `inhibit_rules` block referencing `severity="critical"`. The Phase 5 standardization closes the gap: the inhibit rule fires when needed, and the convention scales to feature 002's warning-tier alerts without another rename pass.

## 2026-05-11 — Phase 5 closure: `DashboardLagBreach` predicate replaced

**Decision**: The Phase 4 `DashboardLagBreach` predicate `time() - max(timestamp(collectmind_diagnostic_findings_received_total)) > 10` had an idle false-positive (no recent sample → infinite lag). Phase 5 replaces it with `max(up{job="orchestration-api"}) == 1 AND max(scrape_duration_seconds{job="orchestration-api"}) > 10`. The replacement is anchored to scrape-target liveness, so the alert can only fire while the target is being scraped, and it measures the actual scrape duration rather than inferring it from sample timestamps. The replacement is documented inline in `rules.yaml` with a backref to the Phase 4 deferral.

**Why this matters**: A false-firing alert is worse than a missing alert — it teaches the on-call to ignore the page. The Phase 4 deferral named the issue explicitly; Phase 5 closed it as part of the severity-tier standardization sweep so the work landed atomically rather than as a stand-alone fix.

## 2026-05-11 — Phase 5 closure: `SoakErrorRateOrMemoryBreach` split into two alerts

**Decision**: The Phase 4 `SoakErrorRateOrMemoryBreach` alert had a title implying error rate OR memory growth but an expression covering only error rate. Phase 5 splits it into `SoakErrorRateBreach` (error rate, unchanged predicate) and `SoakMemoryGrowthBreach` (24-hour RSS delta against orchestration-api). Both share `slo: SC-003` and the `slo-003-soak.md` runbook. The nightly soak workflow (`.github/workflows/nightly.yaml`) asserts the same memory-growth threshold (`(end - start) / start <= 0.05`) as a post-run gate so SC-003 is both a real-time alert and a workflow-tier assertion.

**Why this matters**: SC-003 has two halves in the spec; the rules.yaml surface should match the spec surface so a reviewer reading the alert set sees both halves named. Now: in-flight observability surfaces both halves, and the nightly workflow's post-run gate enforces the memory half against the 24-hour budget that's not measurable in steady-state on PR-tier.

## 2026-05-11 — Compose `scrape_interval` lowered from 15 s to 2 s to honor SC-006

**Decision**: `infra/compose/prometheus.yml`'s `scrape_interval` and `evaluation_interval` lowered to `2s` and `5s` respectively (from `15s` for both). The 15-second default would make T108's "dashboard lag <=10 s" assertion fail by construction (a single scrape interval already exceeds the SLO ceiling). The 2-second scrape rate raises CPU on the local Compose stack but stays well within laptop-class budgets for the foundation smoke.

**Why this matters**: SC-006 expresses a 10-second ceiling on dashboard freshness. Prometheus's scrape interval is a hard floor on that freshness; any scrape interval above 10 seconds violates SC-006 deterministically. The Compose config and the binding SLO are now consistent. Production scrape intervals (managed via the Terraform IaC at T128) inherit the 2-second pin unless an ADR records a deviation. This is a worked example of the user's Phase 4 review note that "the compose change is mechanical; the test stays as-is" — the test was right; the infrastructure needed to catch up.

## 2026-05-09 — The 13 verification fixes in `7dd2723` as the canonical worked example of verify-before-clear

**Decision**: The verification work between Phase 3 implementation (`b9fddc8`) and Phase 3 closure (`7dd2723`, `d5f4aa5`) is the canonical worked example of the verify-before-clear pattern. Future phase closures follow the same shape:

1. Land implementation in one commit (or one feature branch).
2. Run all three test tiers against the real local stack.
3. Triage failures by tier and by root cause (not by file).
4. Fix root causes, rebuild, retest, until the gate is green.
5. Then do the human spot-check on the named load-bearing files.
6. Then commit closure.
7. Then update `PROJECT_STATE.md` and `DECISIONS.md`.

**Why this matters**: It establishes the cadence. Phase 4 closure will be measured against this same shape. The 13-cycle count is not a target; it is a signal that the system is exercised enough that real bugs surface. If a future phase closes with 0 verification cycles, the right question is "what did we miss?" not "how did we get so lucky?"

## 2026-05-11 — Phase 6 closure: T137 no-fabrication call on ADR-0002 eval baseline

**Decision**: The closure session for feature 001 ran on a workstation without GPU access (`nvidia-smi` not on PATH). The Phase 6 T137 task asks for `make eval` to fill ADR-0002's bracketed eval-suite baseline table and promote the ADR from `Proposed` to `Accepted` in a follow-up commit. The user's explicit instruction was: "if no GPU is locally available, skip the actual run and leave ADR-0002 at Proposed with a one-line note documenting the gating. Do not fabricate baseline numbers." That instruction was followed exactly. ADR-0002's first line carries a T137 gating note that names the GPU-runner requirement and points at `.github/workflows/ci-workflow-dispatch.yaml`'s `eval-suite` job. The bracketed rows in the eval-suite baseline table (`[BASELINE_VSS_PASS_RATE]`, `[BASELINE_GEN_LATENCY_P50_MS]`, etc.) remain bracketed.

**Why this matters**: A fabricated baseline that "looks plausible" would propagate through every subsequent eval cycle as the comparison anchor — every regression test would measure drift against a number that was never observed. The cost of fabricating once is exponentially worse than the cost of recording the gating condition and waiting for the real run. This sets a project-wide pattern: when a measurement requires infrastructure that isn't available in the current session, the right move is to document the gating condition in-place, not to estimate. Every numeric claim in an ADR, runbook, or readiness review must be traceable to a real run.

## 2026-05-11 — Phase 6 closure: T136 and T139 record measured numbers, not budgets, as the documentation pattern

**Decision**: Phase 6 T136 (dashboard-lag SLO measurement) and T139 (quickstart end-to-end re-run) both record the *measured* wall-clock numbers from real local runs into the corresponding documentation artifacts (`observability/runbooks/slo-006-dashboard-lag.md` for T136; `docs/runbook/feature-001-readiness-review.md` and `docs/PROJECT_STATE.md` for T139). T136 records max 2.11 s / mean 1.98 s over 5 publications against the SC-006 10 s ceiling. T139 records 27.32 s end-to-end on a warm Compose stack against the SC-008 600 s budget. Both entries include the methodology (sample size, polling cadence, what "warm stack" means) so the measurement is reproducible.

**Why this matters**: The constitution distinguishes "SLOs measured, not aspired" (Principle XI). The documentation pattern that follows from that principle is: every SLO-anchored runbook section names the budget AND the most recent measurement against the budget, with enough methodology to reproduce. Sections that say "p95 must be under 200ms" without a measurement become aspirations; sections that say "p95 was 47ms last measured 2026-05-11 over a 5-minute window" become a contract. This is the third-party-engineer-onboarding test: a new on-call reading the runbook should see both the contract and the latest evidence the contract holds. Future SC-### measurements (the SC-002 / SC-003 / SC-004 numbers gated to workflow_dispatch / nightly tier) inherit this pattern: when the workflow runs, the result lands in the corresponding runbook page alongside the existing budget, not in a separate "stats" file that nobody reads.

## 2026-05-12 — Inaugural PR-tier CI run: semgrep installed via pipx to break otel pin conflict

**Decision**: `semgrep==1.99.0` is removed from the `[dev]` extras in `pyproject.toml` and installed via `pipx install semgrep==1.99.0` as a dedicated step in the `security-static` job of `.github/workflows/ci.yaml`. The version, the project's invocation surface (`semgrep --config p/python --config p/security-audit --error src/collectmind`), and Constitution Principle VII's "Semgrep MUST run in CI" requirement are all unchanged. Only the install path moves from `pip install -e ".[dev]"` (shared resolver) to `pipx install semgrep==1.99.0` (isolated venv).

**Why this matters**: The inaugural PR-tier CI run on the renamed `snts_collectmind` remote (PR #1, feature 001 → main) failed at `pip install -e ".[dev]"` across every job that pulls dev deps. Root cause: `semgrep 1.99.0` requires `opentelemetry-api~=1.25.0` (>=1.25, <1.26); the project pins `opentelemetry-api==1.29.0` for collectmind + sdk + exporters, plus `~=1.27` from `opentelemetry-instrumentation-aiokafka==0.50b0`. The intersection is empty, so pip refuses to resolve. Three plausible fixes: (a) bump semgrep to a version with a relaxed otel constraint and chase its dep graph, (b) replace the step with `returntocorp/semgrep-action`, (c) keep the version and isolate the install. (c) is the right answer because semgrep is a CLI tool, not a runtime library; its transitive deps have no business in the application's resolver. The pipx isolation makes that distinction structural: semgrep's venv is independent of the project's venv, and a future otel bump in either won't reintroduce the same collision. The pattern generalizes — any future CI-only CLI tool with conflicting deps lands via pipx, not via `[dev]`.

This is also a real-world example of the "trust the gate, audit on signal" pattern: the dep conflict was invisible on local dev (`.venv-test` resolved against a cached lockfile from the original install) and only surfaced on the first fresh `pip install -e ".[dev]"` in a clean CI runner. The PR-tier CI is the gate; the gate surfaced the bug; the fix lands in the same PR that's measuring SC-009 for the first time.
