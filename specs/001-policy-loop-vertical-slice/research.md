# Phase 0 Research: Policy-Loop Vertical Slice

**Branch**: `001-policy-loop-vertical-slice` | **Date**: 2026-05-09

This document records the technology and pattern decisions made during Phase 0 of `/speckit-plan`. Every decision lists the choice, the rationale, and the alternatives considered. NEEDS CLARIFICATION items from the Technical Context have been resolved here; remaining uncertainties are recorded with the resolution path.

## R-001: Application language and runtime

- **Decision**: Python 3.11.9, pinned in `.python-version`, `Dockerfile`, and `pyproject.toml`.
- **Rationale**: Constitution Code Quality Standards require Python 3.11; Pydantic v2, LangGraph, FastAPI, vLLM, and outlines all have first-class Python support; the project already commits to ruff + mypy strict.
- **Alternatives considered**: Python 3.12 (rejected: vLLM v0.20.1 wheels are stable on 3.11, less so on 3.12 in pinned-digest deployment); Go (rejected: ecosystem mismatch for SLM tooling); TypeScript (rejected: same ecosystem mismatch and adds a polyglot tax for a single-team project).

## R-002: Stateful agent orchestration

- **Decision**: LangGraph (latest stable) with a single serializable `PolicyGenerationSession` state object.
- **Rationale**: Constitution Principle XII fixes the four-node graph (Orchestrator, Policy Generator, Policy Validator, Policy Deployer); LangGraph's stateful-graph model maps directly onto that, with conditional routing on validation failure into the same retry path the principle requires; state object is auditable and resumable.
- **Alternatives considered**: Hand-rolled state machine (rejected: portfolio-grade discipline expects a named framework; reinventing routing and retry adds risk); Temporal (rejected: heavyweight workflow engine for a four-node loop, adds operational surface area); LangChain Expression Language alone (rejected: no first-class state machine).

## R-003: Default Small Language Model

- **Decision**: `Qwen/Qwen2.5-7B-Instruct` at revision SHA `a09a35458c702b33eeacc393d103063234e8bc28`, Apache-2.0. Per ADR-0002.
- **Rationale**: Open-weight, permissive license (Apache-2.0), `qwen2` mainline architecture in vLLM (no `trust_remote_code`), 7B parameters give materially better structured-output reliability than 3.8B on multi-field schemas. SHA pinning satisfies Principle IX supply-chain controls.
- **Alternatives considered**: Microsoft Phi-4-mini-instruct (MIT, ~3.8B, requires `trust_remote_code`; rejected as default and recorded in ADR-0002 alternatives); larger Qwen2.5-14B-Instruct (rejected: doubles GPU memory, breaks the cost discipline); quantized AWQ/GPTQ variants of the 7B (rejected: deferred until the bf16 baseline fails the latency budget).

## R-004: Inference runtime, GPU profile

- **Decision**: vLLM `v0.20.1`, image digest pinned in `infra/compose/docker-compose.yaml` and the SLM Dockerfile, `bf16` weights, `--guided-decoding-backend outlines`. Per ADR-0002 and ADR-0003.
- **Rationale**: vLLM is the production-grade default for self-hosted inference; v0.20.1 is the latest stable at constitution sign-off; bf16 is Qwen2.5's native weight precision; the `outlines` backend choice is governed by ADR-0003.
- **Alternatives considered**: TGI (Text Generation Inference; rejected: weaker structured-output story than vLLM at this version); SGLang (rejected: less mainline ecosystem coverage at the time of decision); raw `transformers` (rejected: not throughput-grade for sustained ingest).

## R-005: Inference runtime, CPU fallback profile

- **Decision**: llama.cpp release `b9090` with a GGUF `Q4_K_M` build of the same model revision SHA. Served via `llama-cpp-python` HTTP server (OpenAI-compatible). Per ADR-0002.
- **Rationale**: Q4_K_M is the standard quality/throughput balance for 7B models on CPU. Same revision SHA as the GPU profile preserves audit-record interpretability across profiles.
- **Alternatives considered**: ONNX Runtime + Olive (rejected: extra build complexity for a fallback used only in the local quickstart); transformers on CPU (rejected: too slow even for the quickstart); skipping CPU support entirely (rejected: blocks the constitutional quickstart-on-clean-machine quickstart promise for laptops without GPU access).

## R-006: Constrained-decoding library

- **Decision**: `outlines==1.2.13`, Apache-2.0. Per ADR-0003.
- **Rationale**: Decode-time grammar enforcement (logits-mask FSM); first-class Pydantic v2 integration via `outlines.from_pydantic(CollectionPolicySpec)`; same library on both vLLM and llama.cpp profiles, so contract parity is achievable; explicitly named in Constitution Principle XIII.
- **Alternatives considered**: `xgrammar==0.2.0` (vLLM's default backend; rejected as default but kept as a credible fallback); `instructor==1.15.1` (rejected on architectural grounds: post-hoc validation with retry violates Principle XIII); `lm-format-enforcer==0.11.3` (rejected: slower, weaker Pydantic ergonomics, MIT vs project's preferred Apache 2.0).

## R-007: Authentication and authorization

- **Decision**: OAuth2 client-credentials grant per tenant; JWT bearer required on every external endpoint except `/health` and `/ready`; mandatory non-empty `tenant_id` claim populates the composite finding key. Token expiry (`exp`) enforced; PyJWT with cached JWKS. Per Spec Clarifications Q2 and FR-002, FR-002a, FR-018.
- **Rationale**: Standard, well-tooled, supports the per-tenant identity model; no user/password storage in CollectMind; fits the constitutional "every external endpoint authenticated" stance and matches Sonatus's expected OEM deployment patterns.
- **Alternatives considered**: mTLS (deferred to a defense-in-depth follow-up; not blocked); static API keys (rejected: weaker rotation story); SAML (rejected: wrong shape for machine-to-machine integration).
- **Plan-level pin**: issuer URL, JWKS endpoint, key rotation cadence, and acceptable clock skew are environment-configured. Default skew tolerance: 60 seconds. Default JWKS cache TTL: 5 minutes with a forced refresh on signature failure.

## R-008: Canonical signal vocabulary

- **Decision**: COVESA VSS v6.0 (commit SHA `20c609bf95c73b51d483fb8f81a099d1d5b73066`). Per ADR-0001.
- **Rationale**: Latest stable; aligns with Sonatus Foundation's published VSS abstraction; pinned by tag plus commit SHA so audit records remain interpretable after upgrades.
- **Alternatives considered**: VSS v5.1 (rejected: superseded); VSS `master` (rejected: non-deterministic gate); custom vocabulary (rejected: portfolio claim depends on alignment with the open standard Sonatus uses).
- **Plan-level pin**: vocabulary loaded at validator startup from `config/vss/v6.0/signals.yaml`; verified by SHA-256 against `config/vss/v6.0/manifest.sha256`. PII-adjacent branches recorded at `config/vss/v6.0/pii_signals.yaml` and change-controlled by ADR.

## R-009: Persistent storage

- **Decision**: PostgreSQL 16 with the TimescaleDB extension on the same instance. Local: container. Cloud: AWS RDS for PostgreSQL Flexible Server with the TimescaleDB extension. Tables and a `telemetry_observations` hypertable per `data-model.md`.
- **Rationale**: One database engine for the registry, audit log, and time-series telemetry simplifies the operational surface and the backup story. TimescaleDB's continuous aggregates and retention policies fit the 90-day raw-signal retention default. Row-level security is available now and used permissively in feature 001 to avoid a refactor in feature 002.
- **Alternatives considered**: separate Postgres + InfluxDB (rejected: two engines for a single-team project, two backup paths); separate Postgres + ClickHouse (rejected: too heavy for 1,000 events/s/tenant); single Postgres without TimescaleDB (rejected: time-series query performance for the feedback loop will degrade).

## R-010: Hot feature store

- **Decision**: Redis 7. Local: container. Cloud: AWS ElastiCache for Redis. Key shape `vehicle_id:signal_name` in feature 001 (`tenant_id:vehicle_id:signal_name` from feature 002). TTL 24 hours.
- **Rationale**: Sub-10 ms read p95 (per Principle XI) is straightforward with a managed Redis cluster; TTL gives automatic stale-data cleanup; key-shape future-proofs multi-tenant extension.
- **Alternatives considered**: Memcached (rejected: weaker data-structure support for future hot-path additions); DynamoDB (rejected: tail-latency variance harder to control under sustained load); in-process LRU (rejected: not horizontally shareable across application replicas).

## R-011: Event transport

- **Decision**: Apache Kafka in KRaft mode locally; AWS MSK in cloud. Topics: `diagnostic-findings.v1`, `vehicle-telemetry.v1`, `policy-deployments.v1`, `policy-outcomes.v1`. Schemas in AsyncAPI 3.0 documents under `contracts/asyncapi/`.
- **Rationale**: Kafka is named by the reference docs; ordering per partition supports idempotency on the composite finding key; replay capability supports reprocessing during recovery and during clarification of a regressed pipeline.
- **Alternatives considered**: AWS Kinesis (rejected: weaker local-development story; the project's "Compose-up brings the full stack" mandate is harder to satisfy); RabbitMQ (rejected: weaker replay semantics for the feedback loop's reprocessing scenarios); Redis Streams (rejected: would conflate the hot store and the event transport).

## R-012: Cloud target and IaC

- **Decision**: AWS as the cloud target; Terraform as the IaC tool, with state in S3 + DynamoDB locking. Plan-only on every PR touching `infra/`; `terraform apply` only on `workflow_dispatch`. Per Spec Decision D2 and the Section 5 plan prompt.
- **Rationale**: AWS is Sonatus's published production cloud for Collector AI and Automator AI; alignment with that platform is part of the portfolio claim. Terraform is the project-neutral choice (Bicep would tie us to Azure; Pulumi adds a runtime).
- **Alternatives considered**: Azure + Bicep (rejected per Decision D2; recorded in Section 5 plan prompt history); GCP (rejected: Sonatus alignment story is weaker); Pulumi (rejected: Terraform's HCL is the right level of abstraction for an infrastructure plan a stranger can audit).

## R-013: Compute split

- **Decision** (drafted as ADR-0005 alongside this plan): stateless application services (orchestration API, query API, ingest worker, validator, deployer, feedback worker) on **ECS Fargate**. SLM inference (vLLM by default) on **ECS-on-EC2** with a Capacity Provider tied to an Auto Scaling Group of `g5.2xlarge` (or `g6.xlarge` forward-looking) instances. EKS variant under `infra/terraform/eks/` behind a workspace flag for cluster-grade scaling. CPU-fallback SLM (llama.cpp + GGUF) runs on Fargate for environments without GPU access; behavior-equivalent but not SLO-conformant. Per ADR-0002 negative consequences.
- **Rationale**: Fargate gives the lowest operational surface for the stateless tier; ECS Fargate does not support GPUs, so the SLM workload must use ECS-on-EC2 (or EKS with a GPU node group). g5.2xlarge with an A10G (24 GB) is the smallest instance that comfortably fits the 7B bf16 model plus KV cache; g5.xlarge is too tight at sustained throughput.
- **Alternatives considered**: SageMaker endpoints for the SLM (rejected: less control over decoding parameters and image pinning; more expensive at sustained throughput); Lambda (rejected: cold start unacceptable for SLO compliance); Bedrock (rejected: violates Principle XIII's SLM-first stance).

## R-014: Observability stack

- **Decision**:
  - Local: OpenTelemetry SDK with OTLP exporter to Tempo (traces) + Loki (logs) + Prometheus (metrics) + Grafana (dashboard, alerts).
  - Cloud: AWS Distro for OpenTelemetry (ADOT) collector as a sidecar; CloudWatch Logs and Metrics; AWS X-Ray for traces; managed Grafana flag for the dashboard.
- **Rationale**: One OTel SDK in the application; backends differ between local and cloud, so the application code does not change. ADOT is the AWS-supported path for OTel-ingest; CloudWatch is the AWS-native sink; Grafana stays the canonical dashboard surface to keep the project portable.
- **Alternatives considered**: Datadog (rejected: closed-source vendor lock-in for a portfolio project); New Relic (same); pure CloudWatch (rejected: weaker dashboarding story for the end-to-end pipeline panel); pure Tempo+Prom+Grafana in cloud without ADOT (rejected: re-implements ADOT for no benefit).

## R-015: Test framework selection

- **Decision**: pytest + pytest-asyncio (unit and integration); schemathesis (OpenAPI contract); custom AsyncAPI conformance harness in `tests/contract/asyncapi_harness/` (event contract); testcontainers-python (integration spins up the same Compose topology); Locust (load and soak); hypothesis (property-based on validator and schema invariants); pytest-cov (85 percent floor enforced in CI).
- **Rationale**: Industry-standard for Python services. AsyncAPI conformance is project-owned because the public Python tooling for AsyncAPI 3.0 is thinner than for OpenAPI; we accept the maintenance burden because the Kafka contract is too important to leave untested.
- **Alternatives considered**: pact for contract testing (rejected: pact's strength is consumer-driven contracts between services, not OpenAPI/AsyncAPI conformance); Karate (rejected: JVM dependency); k6 instead of Locust for load (rejected: weaker Python test ecosystem integration; Locust scripts can share fixtures with pytest).

## R-016: Deterministic-fingerprint policy-generator stub

- **Decision** (drafted as ADR-0004 alongside this plan): The `PolicyGeneratorClient` interface has a third implementation, `FingerprintStubClient`, that hashes the inbound diagnostic finding into a deterministic SHA-256 fingerprint and returns a canned, schema-valid `CollectionPolicySpec` from a checked-in golden-corpus directory `tests/fixtures/policy_corpus/`. The stub is contract-tested against the real vLLM-backed client at every PR (single fingerprint, 60-second wall budget) and against a broader fingerprint set on `workflow_dispatch`. The stub is the load-tier and soak-tier client per Constitution Principle XIV.
- **Rationale**: The stub lets PR-tier load exercise the full downstream path (validator, registry, deployer, feedback) without invoking the SLM, keeping the PR pipeline under 20 minutes (SC-009) and the CI cost honest. The contract test against the real SLM is the only thing that prevents drift; that test is non-negotiable.
- **Alternatives considered**: pure-mock stub with no contract test (rejected: drift inevitable, violates "no mocked subsystems where a real one is feasible" via the missing contract-test gate); recording-and-replay against the real SLM each PR (rejected: cost and wall-time would breach the SC-009 budget); skipping load on PRs entirely (rejected: SC-002 / SC-003 then run only on workflow_dispatch with no PR signal).

## R-017: Right-to-erasure path

- **Decision**: Erasure requests arrive on a dedicated authenticated query endpoint, are written to an `erasure_requests` audit table, and are dispatched as a tracked job that propagates to the policy registry, the telemetry store (TimescaleDB hypertable), and the audit log. Default completion bound: 30 days (per GDPR Art. 17 best practice; CCPA expects 45 days; the tighter bound is the binding one). The dispatcher distinguishes "erased" (subject row physically removed where lawful) from "redacted" (subject identifiers replaced with a tombstone, used where referential integrity must be preserved for audit).
- **Rationale**: GDPR/CCPA right-to-erasure requirements obligate timely propagation and an auditable trail; FR-020a requires this as a feature-001 capability.
- **Alternatives considered**: deferring erasure entirely to a later feature (rejected: violates Principle X's documentation requirement for erasure paths); soft-delete only (rejected: does not satisfy "right-to-erasure" semantically); hard-delete only (rejected: breaks audit-trail preservation, violates Principle XVII).

## R-018: Code-signing of policy payloads

- **Decision**: At registry-write time, the deployer signs the canonical-form serialized policy payload using a project-owned signing key managed by AWS KMS in cloud and by a `make`-managed local key in development. Signature is stored alongside the policy row. Verification on retrieval is mandatory; a verification failure routes to the dead-letter queue and pages on-call. Updater integration for end-to-end signed-OTA delivery is out of scope for feature 001 (per spec Assumptions).
- **Rationale**: FR-007 requires immutability and lineage, and FR-022 requires alerting on operational anomalies; signing is the integrity primitive that keeps the registry trustworthy under partial-compromise scenarios.
- **Alternatives considered**: deferring all signing to a future feature (rejected: too easy to lose; signing is cheap once and expensive to retrofit); signing with a developer-shared static key (rejected: weakens the supply-chain story); HSM-only signing (rejected: blocks the local quickstart).

## R-019: Threat model coverage in feature 001

- **Decision**: The threat-model document at `docs/security/threat-model.md` is drafted alongside this plan and enumerates at least the three threats already named in the spec (spoofed tenant claim, replayed event, semantic abuse via schema-conformant payload), plus the SLM-supply-chain threats, the prompt-injection threat (where a finding's hypothesis text leaks into the prompt), and the dashboard-leakage threat (where the dashboard exposes more than the operator's `tenant_id`).
- **Rationale**: Spec Assumptions defer the threat model document to plan time; this is plan time. Coverage of the three named threats is required by spec; the additional threats are required by the constitutional posture (Principle IX, X, XIII).
- **Alternatives considered**: STRIDE-only model (rejected: misses the agent-specific threats); LINDDUN-only (rejected: misses the runtime threats); skipping the document (rejected: spec mandates it as a feature-001 deliverable per FR-022 traceability).

## R-020: CI-tier separation and budget

- **Decision**: GitHub Actions has three workflow files. `.github/workflows/ci.yaml` (PR tier) runs lint, type-check, unit, contract (incl. SLMClient against real SLM at one fingerprint), integration (real local stack incl. real SLM in CPU profile to keep CI cost bounded), container build, Trivy, Syft SBOM, Bandit, Semgrep, pip-audit, gitleaks, Locust smoke against the deterministic-fingerprint stub, and `terraform plan`. `.github/workflows/ci-workflow-dispatch.yaml` runs full SLM-driven Locust load (SC-002 verification), the broader SLM contract regression, and `terraform apply` against the dev workspace, all only on `workflow_dispatch`. `.github/workflows/nightly.yaml` runs the 24-hour Locust soak (SC-003 verification) on a self-hosted GPU runner.
- **PolicyGeneratorClient contract-test SLM wall budget**: 60 seconds for the warm path only. Cold start is not measured by this budget. The PR-tier contract job warms the SLM container before the assertion phase begins (a `/info` poll loop until `runtime_info` returns the pinned revision SHA, followed by one discardable warm-up generation against a fixture fingerprint that is not part of the assertion set). Only the post-warmup wall time of the contract assertions counts against the 60-second budget. Cold start (image pull, weight load, FSM compilation) is bounded separately by the readiness-probe timeout in the Compose service definition and is not a per-PR metric. The same separation applies to the contract-test fixture in `tests/contract/test_slm_client_contract.py`: warm-up runs in a session-scoped pytest fixture; the per-test wall budget is only the assertion time.
- **Rationale**: Honors Principle VII (CI/CD gates merges) and Principle XIV (deterministic budgeted model execution) at the same time. The split is the literal expression of those two principles.
- **Alternatives considered**: single workflow with conditional jobs (rejected: workflow dispatch semantics in GitHub Actions are clearer when each set of jobs lives in its own file); running the soak in the PR tier (rejected: budget violation under SC-009); running everything always (rejected: cost violation under Principle VII's model-cost discipline rules).

## R-021: Policy Generator HTTP adapter

- **Decision**: The `policy-generator-client.v1.yaml` `/generate` endpoint is implemented by a thin CollectMind-owned adapter that wraps the underlying inference runtime's native HTTP surface, rather than exposing the runtime directly. On the GPU profile the adapter wraps vLLM's OpenAI-compatible `/v1/chat/completions` and `/v1/completions` endpoints; on the CPU fallback profile it wraps `llama-cpp-python`'s server on the equivalent OpenAI-compatible surface. The adapter is responsible for: (a) translating the project's typed `GenerationRequest` (with explicit `schema`, `decoding`, and `retry_context` fields) into the runtime's native request shape (including the `extra_body.guided_json` field on vLLM and the `response_format`/grammar binding on llama.cpp); (b) projecting the runtime's response into the project's `GenerationResponse` and the audit-record `RuntimeInfo` block; (c) enforcing the deterministic-decoding contract (Principle XIV) by rejecting any request whose `decoding.temperature` is non-zero in CI builds; (d) recording the runtime version, weight SHA, and constrained-decoding library version once at startup and asserting they match the manifests pinned by ADR-0002 and ADR-0003. Both adapter implementations (`VLLMClient`, `LlamaCppClient`) and the deterministic stub (`FingerprintStubClient` per ADR-0004) are contract-tested against the same `policy-generator-client.v1.yaml` schema; drift between them fails the contract tier in CI.
- **Rationale**: A thin adapter, owned by the project, is the smallest surface that lets the orchestration code remain runtime-agnostic while keeping the contract test honest across implementations. Calling vLLM's OpenAI-compatible endpoint directly from the orchestration code would couple the application to a specific runtime's request and response shapes; calling llama.cpp's server with the same client code would force the application to handle two response shapes. Owning the projection in `src/collectmind/slm/` is cheap and keeps `policy-generator-client.v1.yaml` as the single source of truth that all three clients (vLLM, llama.cpp, stub) implement.
- **Alternatives considered**: Direct calls to vLLM's OpenAI-compatible API from the Policy Generator node (rejected: couples orchestration code to a specific runtime, breaks the same-interface contract across CPU and GPU profiles); a runtime-agnostic library (rejected: nothing in the ecosystem covers vLLM and llama.cpp under one Python interface at the level of constrained-decoding semantics this project requires); an MCP-style server abstraction (rejected: extra protocol layer for no benefit, and the project owns both ends of the boundary).

## NEEDS CLARIFICATION resolution log

| Item | Resolution |
|---|---|
| OAuth2 issuer URL | Environment-configured; default left blank in `.env.example`; runbook entry documents the setup. |
| JWKS endpoint location | Same as above; cached for 5 minutes with forced refresh on signature failure. |
| Acceptable clock skew | 60 seconds default (R-007). |
| Erasure completion bound | 30 days default (R-017). |
| ECU capability model | Out of scope for feature 001; deferred to feature 004 with a placeholder YAML at `config/ecu/v0.yaml` referenced but unused. |
| Vector database (Qdrant) | Dropped per Decision D5; no read path planned. |
| GPU runner provisioning for nightly soak | `infra/terraform/ci_runner/` provisions a self-hosted GitHub Actions runner; cost documented; cadence may relax to weekly per a tracked ADR if budget tightens. |

All Phase 0 unknowns are resolved. Phase 1 design proceeds.
