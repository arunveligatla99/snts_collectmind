<!--
SYNC IMPACT REPORT
==================
Version change: none → 1.0.0 (initial ratification)
Modified principles: none (first version)
Added principles:
  I.    Production-Grade by Default
  II.   No Mocked Subsystems Where a Real One Is Feasible
  III.  No TODO, No FIXME, No Deferred Work in Shipped Code
  IV.   Tests Are Load-Bearing
  V.    Observability Is a Functional Requirement
  VI.   Reproducible Local Dev and Deployment
  VII.  CI/CD Gates Merges
  VIII. Documentation a Stranger Could Follow
  IX.   Security as a First-Class Requirement
  X.    Vehicle Telemetry Data Handling
  XI.   Performance SLOs Are Measured, Not Aspired
  XII.  Agent Boundaries
  XIII. SLM-First, Isolated, Swappable Model Boundary
  XIV.  Deterministic, Budgeted Model Execution in CI
  XV.   Edge-Versus-Cloud Split
  XVI.  Contracts Are Machine-Readable and Versioned
  XVII. Audit Is a Feature, Not a Log
  XVIII.Governance and Escalation
Added sections:
  - Code Quality Standards
  - Testing Standards
  - Documentation Standards
  - Observability Standards
  - Governance
Removed sections: none
Templates requiring updates:
  - .specify/templates/plan-template.md  ✅ aligned (reads constitution at runtime via Constitution Check section; no static edits required)
  - .specify/templates/spec-template.md  ✅ aligned (no static constitution references)
  - .specify/templates/tasks-template.md ✅ aligned (no static constitution references)
  - .specify/templates/checklist-template.md ✅ aligned
  - README.md                             ⚠ pending (no README yet; will be created during /speckit-plan or feature 001)
  - docs/quickstart.md                    ⚠ pending (will be created during feature 001)
Follow-up TODOs:
  - ADR-0001 (COVESA VSS version pin) drafted during /speckit-constitution finalization (this phase).
  - ADR-0002 (default SLM: model name, revision SHA, license, runtime, quantization, eval-suite baseline, upgrade and rollback) drafted between /speckit-constitution and /speckit-plan to answer Decision D3.
  - ADR-0003 (constrained-decoding library) drafted between /speckit-constitution and /speckit-plan to answer Decision D4.
  - ADR-0004 (deterministic-fingerprint Policy Generator stub) drafted as part of /speckit-plan output.
  - ADR-0005 (SLM hosting topology on AWS: ECS on EC2 with g5/g6 vs EKS with a GPU node group) drafted as part of /speckit-plan output.
  - docs/adr/README.md (ADR drafting cadence index) created alongside ADR-0001.
-->

# CollectMind Constitution

CollectMind is an agentic vehicle telemetry collection policy engine that sits between a diagnostic reasoning system (AI Technician) and a vehicle data collection control plane (Collector AI). This constitution governs every downstream specification, plan, task list, and implementation. It is the highest-priority artifact in the project. When any plan or task conflicts with a principle below, the principle wins and the plan changes.

If a principle is genuinely impractical for a given feature, the feature MUST record the deviation in an Architecture Decision Record under `docs/adr/` and the deviation MUST be approved before the feature is implemented. Principles IV, VII, IX, X, XI, XIII, and XIV are non-negotiable: deviations require a constitution amendment in a PR, not an ADR.

## Core Principles

### I. Production-Grade by Default

Every feature MUST be shipped to a standard a Sonatus principal engineer would approve in code review. No "demo," "prototype," or "we will harden it later" framing. The first feature is held to the same bar as the last.

**Rationale**: This project is portfolio-grade reference work. Quality decay starts the moment "good enough for now" is accepted once.

### II. No Mocked Subsystems Where a Real One Is Feasible

If the architecture calls for Kafka, the system MUST use Kafka. If it calls for PostgreSQL, the system MUST use PostgreSQL. If it calls for TimescaleDB, the system MUST use TimescaleDB. Mocks are permitted only at clearly external boundaries the team cannot reproduce locally (real vehicle CAN bus, real Collector AI deployment endpoint, real AI Technician). Every mock MUST live behind a documented interface and ship with a contract test that the real adapter must also pass.

**Rationale**: Mocks that diverge from production behavior produce green tests that pass in CI and fail in the field. A real local stack is the only reliable correctness signal.

### III. No TODO, No FIXME, No Deferred Work in Shipped Code

Source files MUST contain no TODO, FIXME, "we will handle this later," or "left as exercise" comments. Deferred concerns MUST live in the spec, in an ADR, or as a tracked GitHub Issue. The CI pipeline MUST reject any PR that introduces these markers.

**Rationale**: Comments rot; trackers do not. Treating deferral as a first-class artifact prevents silent technical debt accumulation.

### IV. Tests Are Load-Bearing (NON-NEGOTIABLE)

Every feature MUST ship unit tests for logic, contract tests for every external interface (OpenAPI for REST, Protobuf for gRPC, AsyncAPI or JSON Schema for events), at least one integration test that exercises the end-to-end signal path against the real local stack including the real SLM container, and at least one load or soak test for any hot path. Coverage floor is 85 percent line coverage on application code, measured by pytest-cov, enforced in CI. Test-driven development posture: tests are written before or alongside implementation, never after the fact.

**Rationale**: Tests are the only durable specification of behavior. Coverage below 85 percent on a codebase this small admits accidental regressions that no human review will catch.

### V. Observability Is a Functional Requirement

Structured JSON logs with correlation IDs, OpenTelemetry traces propagated across service boundaries, RED metrics for every external interface, USE metrics for every owned resource, and a runnable local Grafana dashboard MUST ship with the first feature, not later. Every alert in production MUST have a corresponding runbook section. Logs MUST never include PII, secrets, or raw signal payloads above a configured size. SLM-call observability MUST include prompt template version, model identifier, weight revision SHA, decoding seed, schema-constraint mode, input tokens, output tokens, generation latency, and constraint-violation count.

**Rationale**: A system that cannot be observed cannot be operated. A system that cannot be operated cannot be trusted.

### VI. Reproducible Local Dev and Deployment

`docker compose up` MUST bring the entire stack up on a clean clone, including the SLM inference container. The Compose file MUST pull the inference image at a pinned digest and mount model weights from a host-cached path keyed by weight SHA; first-run weight download MUST be automated and idempotent. A llama.cpp + GGUF Compose profile MUST provide a CPU fallback for laptops without a supported GPU. `make test` MUST run the full test suite. `make load` MUST run the production load profile and assert SLOs. Infrastructure-as-code (Terraform) MUST define every cloud-deployed component, even components that are never deployed to a real cloud. A single make target MUST rebuild the local stack from a clean state in under five minutes after the weights cache is warm.

**Rationale**: A reviewer who cannot run the stack cannot review the system.

### VII. CI/CD Gates Merges (NON-NEGOTIABLE)

GitHub Actions MUST run lint, type-check, unit tests, contract tests, integration tests, container build, dependency vulnerability scan (Trivy for images, pip-audit for Python deps), static security analysis (Bandit and Semgrep), license check, and an SBOM emit (Syft). PRs MUST NOT merge on red CI. The README MUST carry a CI status badge and a coverage badge. SLM-specific CI rules (runtime image digest pin, weight revision SHA pin, decoding seed pin, deterministic-fingerprint stub for load and soak, real-SLM exposure budget on PR, weight cache by SHA, workflow_dispatch gating for full SLM runs) are governed by Principle XIV, which is the authoritative source for those rules.

**Rationale**: Discipline that lives in human attention decays. Discipline encoded in CI does not.

### VIII. Documentation a Stranger Could Follow

README MUST contain: a one-paragraph elevator pitch, a Mermaid architecture diagram, a quickstart that runs in under ten minutes on a clean machine (CPU-fallback profile acceptable for the quickstart), and a link to `/docs`. `/docs` MUST contain an ADR per non-obvious decision in MADR format, an OpenAPI/AsyncAPI/Protobuf contracts directory, and a runbook with one page per known failure mode. A new engineer who has never seen the project MUST be able to ship their first PR in under one day.

**Rationale**: Documentation that requires the original author to interpret it is not documentation.

### IX. Security as a First-Class Requirement (NON-NEGOTIABLE)

Secrets MUST be supplied via environment variables in development and a real secret manager (AWS Secrets Manager) in deployed environments. No secrets in git, ever, enforced by gitleaks in the pre-commit hook and in CI. Dependencies MUST be pinned to exact versions and refreshed on a tracked cadence. SBOM MUST be emitted on every build. Every external API endpoint MUST require authentication; the only exception is the health and readiness endpoints. Input validation on every external surface MUST use Pydantic v2. OWASP Top 10 MUST be considered for every PR touching an HTTP boundary. Model weights are treated as supply-chain artifacts: pinned by revision SHA, downloaded from the official upstream, verified by SHA-256 at download and re-verified at container start, recorded in the SBOM alongside Python dependencies; a digest mismatch MUST fail the readiness probe closed.

**Rationale**: Vehicle telemetry plus PII plus multi-tenant isolation is a non-trivial security surface. Treating security as a checklist item produces a checklist that never fires.

### X. Vehicle Telemetry Data Handling (NON-NEGOTIABLE)

COVESA VSS is the canonical signal vocabulary; signal names that are not valid VSS at the pinned version MUST be rejected. PII-adjacent signals (precise geolocation, driver biometrics, personal usage patterns) MUST require an explicit consent flag in the policy and MUST be blocked otherwise. Per-tenant data isolation MUST be enforced at the API gateway, the database row level, and the deployment client. Retention defaults: 90 days for raw signals in TimescaleDB, indefinite for immutable policy registry rows, both overridable per tenant. GDPR and CCPA right-to-erasure paths MUST be documented and tested. Diagnostic inputs and generated policies MUST never leave the SLM container's process boundary except through documented OpenTelemetry traces and structured logs that are PII-stripped.

**Rationale**: Automotive data carries non-obvious PII. The defaults must err toward strict isolation.

### XI. Performance SLOs Are Measured, Not Aspired (NON-NEGOTIABLE)

The following are binding SLOs verified by the load and soak suites in CI. SLO breach in CI MUST fail the build.

- Diagnostic-event-to-policy-deployed latency: p50 under 4 seconds, p95 under 12 seconds, p99 under 30 seconds.
- Sustained ingest: 1,000 diagnostic events per second per tenant.
- 24-hour soak at 50 percent of peak: no memory leak greater than 5 percent and no error rate greater than 0.1 percent.
- Redis hot-store reads: p95 under 10 ms.
- Validator latency: p95 under 200 ms.

**Rationale**: An SLO that is not measured is a wish. Wishes do not survive contact with production.

### XII. Agent Boundaries

The four LangGraph nodes (Orchestrator, Policy Generator, Policy Validator, Policy Deployer) MUST be the only places agentic decisions are made. No business logic outside the graph. State MUST live in a single PolicyGenerationSession object that is fully serializable, versioned, and queryable for audit. The Policy Generator node MUST be the only node that invokes a language model; the other three nodes MUST be deterministic Python. Validation failures MUST route back to the generator with errors injected into the retry prompt; retry budget MUST be enforced; exhaustion MUST go to a dead-letter queue with a page.

**Rationale**: Agentic behavior is bounded by the graph. Anywhere else, the system is a script that pretends to be intelligent.

### XIII. SLM-First, Isolated, Swappable Model Boundary (NON-NEGOTIABLE)

The Policy Generator node MUST run an open-weight Small Language Model by default. The default model MUST be named in `research.md` by exact Hugging Face revision SHA. Acceptable defaults at constitution sign-off are Microsoft Phi-4-mini-instruct or Qwen2.5-7B-Instruct, both Apache 2.0 licensed; substitutions require an ADR. LLMs (cloud-hosted or otherwise) are an opt-in upgrade path behind the same interface, never the default. This stance mirrors Sonatus AI Director's published support for both SLMs and LLMs and Sonatus's in-vehicle edge AI thesis; it is a load-bearing portfolio claim, not a cost optimization.

The model MUST be served via a real inference runtime, not a stub. Production-equivalent serving uses vLLM with a pinned version. CPU fallback for environments without GPU access uses llama.cpp with a GGUF build of the same model at the same revision SHA. The runtime, the model revision SHA, the quantization profile, and the prompt template version MUST be part of every audit event and every metric label.

Structured output MUST be schema-constrained at decode time, not validated after the fact. Decoding MUST use outlines, instructor, or an equivalent grammar-constrained decoder bound to the CollectionPolicySpec Pydantic v2 schema. A free-text response from the Policy Generator MUST be treated as a runtime fault, not a parse failure, and MUST route to the dead-letter queue.

The Policy Generator node MUST sit behind a `PolicyGeneratorClient` interface with three implementations: a vLLM client (default), an llama.cpp client (CPU fallback, contract-equivalent), and an LLM client stub that fails fast with not-implemented unless explicitly enabled by configuration. All three MUST pass the same contract test, which is the gate that lets a future cloud-LLM adapter ship without changing the graph. The model MUST run in an isolated container with no outbound network access except to the configured observability endpoints; it MUST NOT reach the registry, Kafka, or any external service directly.

Model weights MUST be pinned by revision SHA, cached as a CI artifact, and verified by checksum on container start. A weight mismatch MUST fail the readiness probe. Model and runtime upgrades require an ADR that records the prior and new revision SHAs, the eval-suite delta, and the rollback procedure.

**Rationale**: An SLM that runs on the same trust boundary as a vehicle ECU is the right portfolio claim for a Sonatus interview. A SaaS LLM dependency is not.

### XIV. Deterministic, Budgeted Model Execution in CI (NON-NEGOTIABLE)

Continuous integration MUST run real model inference where the contract demands it and MUST run a deterministic substitute where it does not. The split is binding.

Contract tests and integration tests for the Policy Generator node MUST run against the real SLM via vLLM with temperature zero, a fixed seed, a fixed sampling configuration, and a pinned model revision SHA. Outputs MUST be verified against the CollectionPolicySpec schema and against golden examples checked into the repository. These tests MUST be deterministic; non-determinism in the SLM path MUST be treated as a regression and MUST gate the merge.

Smoke load tests, full-profile load tests, and soak tests MUST NOT invoke the SLM. They MUST use a deterministic `PolicyGeneratorClient` stub keyed by input fingerprint, returning canned, schema-valid CollectionPolicySpec payloads that exercise the full downstream path (validation, registry, deployer, feedback). The stub MUST be implementation behind the same interface, contract-tested against the real client, so it cannot drift.

Full SLM-driven load runs, eval-suite runs against the live model, and any benchmark that exercises model latency or quality MUST be gated on a manual `workflow_dispatch` trigger and a documented runbook entry. They MUST NOT run on every PR. They MUST run before tagging a release and on a scheduled cadence recorded in the runbook.

Every CI job that loads model weights MUST record the revision SHA, the runtime version, the quantization profile, and the wall-clock load time as build artifacts. A weight cache miss greater than once per day MUST be treated as a CI infrastructure incident, not a flake.

**Rationale**: Real-model CI is the only honest signal of system correctness; deterministic substitutes are the only sustainable signal of throughput. Both are required; neither replaces the other.

### XV. Edge-Versus-Cloud Split

CollectMind MUST run entirely in the cloud control plane. The only vehicle-side artifact MUST be the deployed policy payload, which MUST be kilobyte-scale, code-signed at registry-write, and rollback-capable through the `deployment_targets` history. No code may be generated for vehicle execution; that boundary belongs to Foundation and Updater.

**Rationale**: Sonatus's existing products own the vehicle runtime. CollectMind's value is at the cloud seam, not on the vehicle.

### XVI. Contracts Are Machine-Readable and Versioned

REST surfaces MUST be OpenAPI 3.1 documents in `contracts/openapi/`. Event schemas MUST be AsyncAPI 3.0 documents in `contracts/asyncapi/`. Internal RPC, if any, MUST be Protobuf in `contracts/proto/`. Contract tests MUST be generated from these artifacts and MUST run in CI. Breaking changes MUST require a version bump and a migration ADR. The Policy Generator's structured-output schema (CollectionPolicySpec) is itself a contract: changes MUST require a Pydantic-model version bump, a prompt-template version bump, and an ADR.

**Rationale**: A contract that is not machine-readable is a suggestion. A contract that is not versioned is a trap.

### XVII. Audit Is a Feature, Not a Log

Every policy in the registry MUST be immutable, semver-versioned, and lineage-tagged with the diagnostic session, anomaly, vehicle scope, and outcome record. Auditors MUST be able to query "which policies touched this vehicle in the last 30 days and why" via a documented API. Audit queries MUST NOT require log-mining. Every audit record MUST carry the SLM identifier, weight revision SHA, prompt template version, and decoding seed used to produce the policy.

**Rationale**: OEM customers will require a defensible audit trail. Building audit as a query surface is the only path to that defensibility.

### XVIII. Governance and Escalation

When a downstream plan or task list proposes lowering any principle above, the proposing artifact MUST record the conflict in an ADR with: the principle, the proposed deviation, the reason, the mitigation, and an explicit approval signature from the author. The author's signature is a binding self-review; reviewers MAY reject. Principles IV, VII, IX, X, XI, XIII, and XIV cannot be deviated from, period; deviations there require the constitution itself to be amended in a PR with reviewer approval.

**Rationale**: Constitution drift is silent and gradual. A friction point at every deviation makes drift visible.

## Code Quality Standards

- Python 3.11. ruff for linting, ruff-format for formatting, mypy in strict mode for typing. Configs committed at repo root. Pre-commit hook MUST enforce all three.
- Pydantic v2 models for every external boundary and for every state object.
- Dependency injection via FastAPI's `Depends()` and explicit factory functions; no module-level globals except for genuinely immutable constants and the OpenTelemetry tracer.
- Small modules, single responsibility, public surface documented with docstrings; private helpers prefixed with underscore and not exported.
- Error handling MUST distinguish Recoverable, Fatal, and Validation classes; each MUST have a documented retry posture.

## Testing Standards

- pytest with pytest-asyncio for async tests.
- Contract tests generated from OpenAPI and AsyncAPI artifacts using schemathesis or equivalent; the `PolicyGeneratorClient` contract test MUST run against the real SLM container with a fixed fingerprint and a 60-second wall budget.
- Integration tests run against the real docker compose stack via testcontainers-python, including the real SLM container.
- Load tests authored in Locust; soak tests are long-running Locust scenarios pinned to a 24-hour window in nightly CI on a self-hosted GPU runner.
- Smoke load on PRs uses the deterministic-fingerprint stub described in Principle XIV; full SLM-driven load runs on `workflow_dispatch` and on the nightly schedule.
- pytest-cov MUST enforce the 85 percent floor; coverage report uploaded as a CI artifact.

## Documentation Standards

- README at repo root with the elevator pitch, architecture diagram (Mermaid), quickstart, status badges, license.
- `/docs/adr/` in MADR format, sequentially numbered. The drafting cadence and the relationship between each ADR and the spec-kit phases is recorded in `/docs/adr/README.md`, which is the authoritative index.
  - ADR-0001 pins COVESA VSS.
  - ADR-0002 records the chosen default SLM (model name, revision SHA, license, runtime, quantization, eval-suite baseline) and the upgrade-and-rollback procedure.
  - ADR-0003 selects the constrained-decoding library.
  - ADR-0004 documents the deterministic-fingerprint Policy Generator stub.
  - ADR-0005 records the SLM hosting topology on AWS (ECS on EC2 with g5/g6 vs EKS with a GPU node group) and the rationale.
- `/docs/runbook/` with one page per alert and one page per known failure mode, including SLM container OOM, SLM weight digest mismatch, vLLM healthcheck failure, CPU-fallback activation, and GPU node group capacity exhaustion.
- `/contracts/` for all machine-readable contracts, including the `PolicyGeneratorClient` OpenAPI document and the `CollectorAIClient` OpenAPI document.
- API reference MUST be generated from FastAPI's OpenAPI on every build and committed to `/docs/api/`.

## Observability Standards

- Logs in JSON, with timestamp, level, service, trace_id, span_id, tenant_id (where applicable), message, and structured fields. No string interpolation of user input.
- Traces via OpenTelemetry SDK, exported to a local Tempo (or Jaeger) in dev and to AWS Distro for OpenTelemetry (ADOT) in deployed environments.
- Metrics via OpenTelemetry, exported to a local Prometheus in dev and to CloudWatch via ADOT in deployed environments. RED for every interface, USE for every queue and pool. Required metrics: `policy_generation_latency`, `validation_pass_rate`, `deploy_success_rate`, `retry_rate`, `hypothesis_confirmation_rate`, `ingest_lag`, `dead_letter_count`, `slm_generation_latency`, `slm_constraint_violation_count`, `slm_weight_sha_active`, `slm_runtime_image_digest_active`.
- One Grafana dashboard MUST tell the CollectMind story end-to-end and MUST include an SLM panel: per-call latency, tokens, constraint-violation rate, active weight SHA, active runtime image digest.

## Governance

This constitution supersedes all other practices. It is loaded by every `/speckit-specify`, `/speckit-plan`, `/speckit-tasks`, and `/speckit-implement` run. Conflicts MUST be resolved in favor of the constitution.

Amendments require a PR that touches this file and an ADR explaining the change. The PR description MUST list every dependent template, ADR, runbook entry, and code path that needs to be updated, and the PR MUST land all of those updates atomically. Reviewers MUST verify that no template or downstream artifact still references a superseded principle.

Versioning policy:
- MAJOR: backward incompatible governance or principle removals or redefinitions.
- MINOR: a new principle or section is added or guidance is materially expanded.
- PATCH: clarifications, wording, typo fixes, non-semantic refinements.

Compliance review: every PR MUST verify that touched code, tests, and documentation align with the principles above. The reviewer MUST cite the principle that gates the change in the PR description when the change is principle-driven (security, observability, SLO, contracts, audit). Use this constitution and `docs/adr/README.md` for runtime development guidance.

**Version**: 1.0.0 | **Ratified**: 2026-05-09 | **Last Amended**: 2026-05-09
