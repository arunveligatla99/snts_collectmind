# Implementation Plan: Policy-Loop Vertical Slice

**Branch**: `001-policy-loop-vertical-slice` | **Date**: 2026-05-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-policy-loop-vertical-slice/spec.md`

## Summary

Deliver an end-to-end vertical slice of the CollectMind policy engine: ingest a single brake-wear diagnostic finding through an authenticated event interface; generate a typed `CollectionPolicySpec` with a self-hosted Small Language Model under schema-constrained decoding; validate against the canonical signal vocabulary (COVESA VSS v6.0); persist as an immutable, versioned, lineage-tagged record in a registry; deploy via a documented downstream interface (in-process simulator stands in for Collector AI); after the simulated collection window closes, evaluate the synthesized telemetry against the hypothesis and write an outcome record. Every operation is observable in a single Grafana dashboard, paged on SLO breach with linked runbook entries, and gated by a tiered CI pipeline (PR-tier under 20 minutes; full SLM eval, full-profile load, and 24-hour soak gated to `workflow_dispatch` and a nightly schedule).

Technical approach: a Python 3.11 service running on AWS, structured around a four-node LangGraph stateful graph (Orchestrator, Policy Generator, Policy Validator, Policy Deployer) with a single serializable `PolicyGenerationSession` state object. The model boundary is SLM-first (Qwen2.5-7B-Instruct, Apache-2.0, pinned by Hugging Face revision SHA per ADR-0002). Production-equivalent serving runs vLLM v0.20.1 with `--guided-decoding-backend outlines` (per ADR-0003) on ECS-on-EC2 g5/g6 instances; CPU fallback runs llama.cpp `b9090` with a GGUF Q4_K_M build of the same revision SHA on Fargate. Stateless application services (orchestration API, query API, ingest worker, validator, deployer, feedback worker) run on ECS Fargate. Stateful services use AWS managed equivalents: RDS PostgreSQL 16 with TimescaleDB extension, ElastiCache for Redis, MSK for Kafka. Infrastructure-as-code is Terraform, plan-only in PR CI, `apply` only on `workflow_dispatch`. Every external interface has a machine-readable contract (OpenAPI 3.1 or AsyncAPI 3.0) and contract-tested gate. The deterministic-fingerprint policy-generator stub (locked by ADR-0004) lets the PR-tier load suite exercise the full downstream path without invoking the SLM, keeping the PR-tier budget honest under Principle XIV.

## Technical Context

**Language/Version**: Python 3.11.9; pinned in `.python-version`, `Dockerfile`, and `pyproject.toml`.

**Primary Dependencies**:
- Application: FastAPI (latest stable), Pydantic v2 (latest 2.x), LangGraph (latest stable), httpx, structlog, OpenTelemetry SDK with OTLP exporter.
- Model serving: vLLM `v0.20.1` (GPU profile, default), llama.cpp `b9090` with `llama-cpp-python` HTTP server (CPU profile).
- Constrained decoding: `outlines==1.2.13` (per ADR-0003), wired via `--guided-decoding-backend outlines` on vLLM and `outlines.models.llamacpp` on the CPU profile.
- Authentication: PyJWT for JWT verification with JWKS caching (issuer URL and JWKS endpoint resolved from environment configuration).

**Storage**:
- PostgreSQL 16 with the TimescaleDB extension. Tables: `tenants`, `diagnostic_findings`, `vehicle_groups`, `collection_policies` (immutable), `deployment_targets`, `policy_outcomes`, `audit_events`, `erasure_requests`. TimescaleDB hypertable: `telemetry_observations`. Row-level security enabled (permissive in feature 001; restrictive in feature 002).
- Redis 7 for the hot feature store. Key shape `vehicle_id:signal_name` in feature 001 (`tenant_id:vehicle_id:signal_name` in feature 002). TTL 24 hours.
- Apache Kafka (KRaft mode locally, MSK in AWS) for event transport. Topics: `diagnostic-findings.v1`, `vehicle-telemetry.v1`, `policy-deployments.v1`, `policy-outcomes.v1`. Schemas in `contracts/asyncapi/`.
- AWS S3 for SLM weight cache (immutable, versioned, server-side encrypted), build artifacts, and SBOM uploads.

**Testing**: pytest with pytest-asyncio for async tests; hypothesis for property-based tests on the validator and on schema invariants; schemathesis for OpenAPI contract tests; a project-owned AsyncAPI conformance harness for events; testcontainers-python for integration tests against the real local stack including the real SLM container; Locust for load and soak; `pytest-cov` enforces the 85 percent coverage floor.

**Target Platform**:
- Local development: Docker Compose v2 brings up Postgres-with-TimescaleDB, Redis, Kafka (KRaft, single broker), Tempo, Loki, Prometheus, Grafana, the SLM inference container (vLLM by default; Compose profile `cpu` swaps to llama.cpp), and the CollectMind services. `make up` is the entrypoint.
- Cloud: AWS, US East 1 by default. Compute split per ADR-0005 (placeholder, finalized in `/speckit-plan` output here): stateless app services on ECS Fargate; SLM inference on ECS-on-EC2 with a Capacity Provider tied to an Auto Scaling Group of `g5.2xlarge` or `g6.xlarge` instances; stateful services on the AWS managed equivalents named above. EKS variant exists under `infra/terraform/eks/` behind a workspace flag for cluster-grade scaling.

**Project Type**: Cloud control-plane web service with multiple internal microservices, a model inference container, and an observability stack.

**Performance Goals** (binding, per Constitution Principle XI and Spec SC-001 to SC-006, SC-010, SC-012):
- Diagnostic-event-to-policy-deployed: p50 ≤ 4 s, p95 ≤ 12 s, p99 ≤ 30 s, measured under SC-002's load profile.
- Sustained ingest: 1,000 diagnostic events/s/tenant for 30 minutes at end-to-end success ≥ 99.9 percent (workflow_dispatch tier per Principle XIV).
- 24-hour soak at 50 percent of peak: memory growth ≤ 5 percent, error rate ≤ 0.1 percent (workflow_dispatch tier per Principle XIV).
- Operator query: p95 ≤ 200 ms at 100 reads/s.
- Validator: p95 ≤ 200 ms.
- Redis hot-store reads: p95 ≤ 10 ms.
- Outcome record written within 5 minutes of collection-window close.
- Inbound and query API monthly availability ≥ 99.9 percent (~43 min/month).

**Constraints**:
- Principle XIII: model boundary is SLM-first, isolated, swappable. Frontier-LLM SaaS is opt-in and gated by a constitution-amendment ADR.
- Principle XIV: contract and integration tiers run the real SLM under deterministic decoding (`temperature=0`, fixed seed); load and soak tiers use the deterministic-fingerprint stub locked by ADR-0004.
- Principle X: COVESA VSS v6.0 is the canonical signal vocabulary (per ADR-0001). Validator rejects any non-VSS signal. PII-adjacent signals require an explicit consent flag.
- Principle IX: secrets via AWS Secrets Manager in deployed environments and `.env` (gitignored) locally. SBOM emitted on every build by Syft. Trivy scans the application image and the SLM image. Bandit/Semgrep/pip-audit run in CI. Model weights pinned by SHA-256 manifest at `config/slm/qwen2.5-7b-instruct/manifest.sha256`; readiness probe fails closed on digest mismatch. Gitleaks pre-commit and CI.
- Principle XII: agentic decisions only inside the four-node graph; the Policy Generator is the only node that calls the SLM.
- Principle XV: CollectMind runs entirely in the cloud control plane; vehicle-side artifacts are signed kilobyte-scale policy payloads only.

**Scale/Scope**:
- Feature 001: single tenant; single hypothesis class (`brake-wear-early-stage`); synthetic upstream and downstream; logical-time scheduling with environment-scoped time-acceleration factor (per FR-009a).
- Multi-tenant interface preserved: composite finding key `(tenant_id, finding_id)` from day one (per Clarifications Q1).
- Production-equivalent serving sized for 1,000 events/s/tenant; horizontal scale-out via additional GPU nodes in the SLM Auto Scaling Group is recorded in the runbook.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Gates evaluated against `.specify/memory/constitution.md` v1.0.1.

| # | Principle | Status | Justification |
|---|---|---|---|
| I | Production-Grade by Default | PASS | Plan ships dashboards, IaC, security gates, contracts, and full test pyramid in feature 001. |
| II | No Mocked Subsystems Where a Real One Is Feasible | PASS | Real Kafka, Postgres+Timescale, Redis, vLLM in CI integration. Mocks only at AI Technician (upstream simulator) and Collector AI (downstream simulator), each behind a documented interface and contract-tested. |
| III | No TODO, No FIXME, No Deferred Work in Shipped Code | PASS | CI grep gate added to PR pipeline; deferred concerns live in spec Assumptions, ADRs, or GitHub Issues. |
| IV | Tests Are Load-Bearing (NON-NEGOTIABLE) | PASS | Unit, contract (OpenAPI/AsyncAPI/SLMClient), integration with the real local stack including the real SLM container, and load/soak tiers all defined; coverage floor 85 percent enforced by pytest-cov in CI. |
| V | Observability Is a Functional Requirement | PASS | Structured logs, OTel traces and metrics, Grafana dashboard, Alertmanager rules with runbook links, all in feature 001. SLM observability fields per Constitution and ADR-0002. |
| VI | Reproducible Local Dev and Deployment | PASS | `docker compose up` + `make test` + `make load` defined; vLLM image digest pinned, weights cached and SHA-verified. CPU fallback Compose profile available. |
| VII | CI/CD Gates Merges (NON-NEGOTIABLE) | PASS | GitHub Actions runs lint, mypy, unit, contract, integration, container build, Trivy, pip-audit, gitleaks, Bandit, Semgrep, Syft SBOM, Locust smoke (deterministic stub) on every PR. SLM-specific CI rules per Principle XIV. |
| VIII | Documentation a Stranger Could Follow | PASS | README + Mermaid diagram + quickstart + ADRs (0001 through 0005) + runbooks; quickstart target ≤ 10 min on a clean machine. |
| IX | Security as a First-Class Requirement (NON-NEGOTIABLE) | PASS | OAuth2 client-credentials JWT (Clarifications Q2); FR-002a (token expiry); FR-020a (right-to-erasure); supply-chain controls and SBOM per Principle IX; threat model named with three threats (spec) and full doc deferred to `docs/security/threat-model.md`. |
| X | Vehicle Telemetry Data Handling (NON-NEGOTIABLE) | PASS | VSS v6.0 pinned (ADR-0001); PII signal list versioned at `config/vss/v6.0/pii_signals.yaml`; per-tenant isolation hooks at gateway, DB row, deployment client; 90-day raw-signal retention default. |
| XI | Performance SLOs Are Measured, Not Aspired (NON-NEGOTIABLE) | PASS | All SC-### performance targets are tied to specific test tiers; SLO breach in CI fails the build. |
| XII | Agent Boundaries | PASS | Four-node LangGraph; Policy Generator is the only node that invokes the SLM; the other three are deterministic Python; retry routing on validation failure with bounded retry budget and dead-letter queue. |
| XIII | SLM-First, Isolated, Swappable Model Boundary (NON-NEGOTIABLE) | PASS | Qwen2.5-7B-Instruct pinned by SHA (ADR-0002); vLLM + llama.cpp via the same `PolicyGeneratorClient` interface; SLM container has no outbound network except observability; LLM client stub fails fast unless explicitly enabled. |
| XIV | Deterministic, Budgeted Model Execution in CI (NON-NEGOTIABLE) | PASS | Real SLM in contract and integration tiers under `temperature=0` + fixed seed + golden examples; deterministic-fingerprint stub for load and soak (ADR-0004); full SLM-driven load and soak gated to workflow_dispatch and nightly. |
| XV | Edge-Versus-Cloud Split | PASS | CollectMind runs entirely in cloud control plane; the only vehicle-side artifact is the kilobyte-scale signed policy payload. |
| XVI | Contracts Are Machine-Readable and Versioned | PASS | OpenAPI 3.1 in `contracts/openapi/`, AsyncAPI 3.0 in `contracts/asyncapi/`, Pydantic v2 schema for `CollectionPolicySpec` versioned alongside prompt template. |
| XVII | Audit Is a Feature, Not a Log | PASS | FR-017a enumerates the audit-record minimum field set (composite finding id, SLM repo + revision, prompt template version, decoding seed, policy version, deployment record ref, outcome ref). Audit query API is part of the orchestration query interface. |
| XVIII | Governance and Escalation | PASS | No deviations proposed in this plan; if any arise during `/speckit-tasks` or `/speckit-implement`, an ADR is the required vehicle. |

**Gate verdict**: PASS. No deviations to record. Complexity Tracking section is empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-policy-loop-vertical-slice/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── openapi/
│   │   ├── orchestration-api.v1.yaml
│   │   ├── query-api.v1.yaml
│   │   ├── policy-generator-client.v1.yaml
│   │   └── collector-ai-client.v1.yaml
│   └── asyncapi/
│       ├── diagnostic-findings.v1.yaml
│       ├── vehicle-telemetry.v1.yaml
│       ├── policy-deployments.v1.yaml
│       └── policy-outcomes.v1.yaml
├── checklists/
│   ├── requirements.md
│   ├── security.md
│   ├── observability.md
│   └── testing.md
├── spec.md
└── tasks.md             # Phase 2 (/speckit-tasks output - not created here)
```

### Source Code (repository root)

```text
src/collectmind/
├── ingest/                   # Inbound HTTP and Kafka consumer for diagnostic-findings.v1
├── auth/                     # JWT verification, JWKS caching, tenant claim extraction
├── graph/                    # LangGraph state and four nodes
│   ├── orchestrator.py
│   ├── policy_generator.py
│   ├── policy_validator.py
│   ├── policy_deployer.py
│   └── session.py            # PolicyGenerationSession state object
├── slm/                      # PolicyGeneratorClient interface + vLLM, llama.cpp, LLM-stub adapters
├── validator/                # VSS v6.0 lookup, ECU capability stub (feature 004 hardens), PII consent
├── registry/                 # Immutable policy registry, semver, lineage queries
├── deployer/                 # CollectorAIClient interface + simulator and real-stub adapters
├── feedback/                 # Window-close handler, hypothesis evaluation, outcome writer
├── query/                    # Operator query API (policy, version history, deployment, outcome)
├── erasure/                  # GDPR/CCPA right-to-erasure paths across registry, telemetry, audit
├── observability/            # OTel setup, structured logging config, RED/USE metric middleware
└── app.py                    # FastAPI app composition

contracts/
├── openapi/                  # Mirrors the spec dir, source of truth lives here
└── asyncapi/

infra/
├── compose/                  # docker-compose.yaml, Compose profiles (default, cpu, dev)
└── terraform/
    ├── networking/           # VPC, subnets, NAT, security groups
    ├── compute/              # ECS Fargate (app), ECS-on-EC2 g5/g6 (SLM), EKS variant gated by workspace
    ├── data/                 # RDS Postgres+Timescale, ElastiCache Redis, MSK
    ├── storage/              # S3 (weight cache, artifacts, SBOM)
    ├── secrets/              # Secrets Manager, IAM roles
    └── observability/        # ADOT collector, CloudWatch wiring, managed Grafana flag

config/
├── vss/v6.0/                 # signals lookup, manifest.sha256, pii_signals.yaml
└── slm/qwen2.5-7b-instruct/  # manifest.sha256 for weights, GGUF artifact pin

prompts/
└── policy_generator/v1.0.0/  # System and user prompt templates, semver-versioned

models/
└── README.md                 # Pointer to manifest; weights are not committed; downloaded by build

observability/
├── grafana/dashboards/       # CollectMind end-to-end dashboard JSON
├── prometheus/               # Alert rules, recording rules
└── runbooks/                 # One markdown page per alert and per known failure mode

docs/
├── adr/                      # ADR-0001..ADR-0005 already drafted; ADR-0004, ADR-0005 land here
├── runbook/                  # Operational runbooks
├── api/                      # FastAPI-generated OpenAPI rendering
└── security/threat-model.md  # Threat model document (drafted under this feature)

tests/
├── unit/
├── contract/                 # schemathesis (REST), AsyncAPI conformance harness, SLMClient contract
├── integration/              # testcontainers-python, real SLM container exercised
└── load/                     # Locust scenarios: smoke (deterministic stub), full (real SLM, workflow_dispatch), soak (workflow_dispatch nightly)

.github/workflows/            # ci.yaml (PR tier), ci-workflow-dispatch.yaml (full SLM, load, soak), nightly.yaml
```

**Structure Decision**: Single-repo, multi-module Python service ("Option 1: Single project") with explicit separation of `src/collectmind/`, `contracts/`, `infra/`, `observability/`, `prompts/`, `config/`, and `tests/`. Microservice-style boundaries are preserved as Python packages under `src/collectmind/`; deployment topology splits them across ECS services in Terraform. The SLM is a separate container (vLLM image with weights baked in by build, verified at start) reached via the `PolicyGeneratorClient` HTTP interface; it is operationally and architecturally a different artifact from the rest of the application code, even though it lives in the same repo.

## Complexity Tracking

> Constitution Check passed without violations. No entries.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| (none) | | |
