---

description: "Task list for feature 001 implementation"
---

# Tasks: Policy-Loop Vertical Slice

**Input**: Design documents from `/specs/001-policy-loop-vertical-slice/`
**Prerequisites**: plan.md (✓), spec.md (✓), research.md (✓), data-model.md (✓), contracts/ (✓), quickstart.md (✓), ADR-0001..ADR-0005 (✓)

**Tests**: Test tasks are included. They are mandatory for this feature per Spec FR-021 and Constitution Principle IV (Tests Are Load-Bearing, NON-NEGOTIABLE). Tests-first per Principle IV: tests are written before or alongside implementation, never after.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story tag (US1, US2, US3) for tasks in user-story phases
- File paths are absolute relative to the repo root.

## Path Conventions

Single project with multi-module Python service. Source under `src/collectmind/`. Tests under `tests/`. Contracts under `contracts/` (mirroring `specs/001-policy-loop-vertical-slice/contracts/`). Infrastructure under `infra/`. Observability under `observability/`. Configuration under `config/` and `prompts/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffolding, tooling, local stack scaffold.

- [X] T001 Create repository directory tree per `plan.md` (Project Structure section): `src/collectmind/{ingest,auth,graph,slm,validator,registry,deployer,feedback,query,erasure,observability,simulators,kafka,redis}/`, `tests/{unit,contract,integration,load}/`, `contracts/{openapi,asyncapi}/`, `infra/{compose,terraform/{networking,compute,data,storage,secrets,observability,ci_runner,eks}}/`, `observability/{grafana/dashboards,prometheus,runbooks}/`, `config/{vss/v6.0,slm/qwen2.5-7b-instruct,ecu}/`, `prompts/policy_generator/v1.0.0/`, `models/`, `docs/{adr,runbook,api,security,examples}/`, `scripts/`. Mirror `specs/001-policy-loop-vertical-slice/contracts/` into the repo-root `contracts/` directory. <!-- 50ade89 -->
- [X] T002 [P] Create `pyproject.toml` with Python 3.11.9 pin and exact-pinned runtime deps (FastAPI, Pydantic v2, LangGraph, httpx, structlog, OpenTelemetry SDK + OTLP exporter, PyJWT, outlines==1.2.13, vllm==0.20.1 (extras only on GPU profile), llama-cpp-python, ulid-py, asyncpg, redis-py, aiokafka, pydantic-settings) and dev deps (pytest, pytest-asyncio, pytest-cov, hypothesis, schemathesis, locust, testcontainers, ruff, mypy, bandit, semgrep, pip-audit). Include `uv.lock` in repo. <!-- 50ade89 -->
- [X] T003 [P] Create `ruff.toml` with project-wide lint and `ruff format` configuration (line length, target-version py311). <!-- 50ade89 -->
- [X] T004 [P] Create `mypy.ini` configured in strict mode (`strict = True`, `warn_unused_ignores = True`, `disallow_any_explicit = True`, `python_version = 3.11`). <!-- 50ade89 -->
- [X] T005 [P] Create `.pre-commit-config.yaml` with hooks: ruff, ruff-format, mypy, gitleaks, the no-TODO/FIXME guard at `scripts/check_no_todo_fixme.py` (per Principle III). <!-- 50ade89 -->
- [X] T006 [P] Create `.gitignore` (Python defaults, `.env`, `models/weights/`, `reports/`, build artifacts, IDE files). <!-- 50ade89 -->
- [X] T007 [P] Create `.editorconfig` (UTF-8, LF line endings, 4-space Python indent, 2-space YAML indent). <!-- 50ade89 -->
- [X] T008 [P] Create `LICENSE` (Apache-2.0). <!-- 50ade89 -->
- [X] T009 [P] Create `README.md` skeleton at repo root with pitch, badges (CI, coverage), Mermaid diagram placeholder, link to `/docs`, link to `specs/001-policy-loop-vertical-slice/quickstart.md`. <!-- 50ade89 -->
- [X] T010 [P] Create `Makefile` at repo root with targets: `up`, `down`, `wait-ready`, `clean`, `clean-weights`, `test`, `test-unit`, `test-contract`, `test-integration`, `load-smoke`, `load-full`, `soak`, `eval`, `lint`, `typecheck`, `coverage`. <!-- 50ade89 -->
- [X] T011 Create `infra/compose/docker-compose.yaml` with services: `postgres-timescale`, `redis`, `kafka` (KRaft single broker), `tempo`, `loki`, `prometheus`, `grafana`, `mock-issuer` (OAuth2), `slm-inference` (vLLM image at pinned digest), `collector-ai-simulator`, and CollectMind app services (`orchestration-api`, `query-api`, `ingest-worker`, `validator`, `deployer`, `feedback-worker`). Define Compose profiles: `default` (vLLM), `cpu` (llama.cpp). <!-- 50ade89 -->
- [X] T012 [P] Create `infra/compose/grafana-provisioning/{dashboards,datasources}/` with auto-provisioning files referencing `observability/grafana/dashboards/collectmind-end-to-end.json` and Prometheus/Loki/Tempo datasources. <!-- 50ade89 -->
- [X] T013 [P] Create `infra/compose/prometheus.yml` scrape configuration for the CollectMind services and the SLM container. <!-- 50ade89 -->
- [X] T014 [P] Create `infra/compose/loki-config.yml` and `infra/compose/tempo-config.yml`. <!-- 50ade89 -->
- [X] T015 [P] Create `infra/compose/issuer-config.yaml` seeding the mock OAuth2 issuer with the `feature-001-default` tenant client. <!-- 50ade89 -->
- [X] T016 [P] Create `infra/compose/cpu-profile/Dockerfile.llamacpp` for the CPU-fallback SLM container (llama-cpp-python server + GGUF Q4_K_M build). <!-- 50ade89 -->
- [X] T017 [P] Create `infra/compose/gpu-profile/Dockerfile.vllm` pinning the vLLM v0.20.1 base image by digest, baking the weights at build, verifying the SHA-256 manifest at start; readiness probe fails closed on digest mismatch (per ADR-0002). <!-- 50ade89 -->
- [X] T018 [P] Create `.env.example` with `OAUTH2_ISSUER_URL`, `OAUTH2_AUDIENCE`, `SLM_PROFILE`, `TIME_ACCELERATION_FACTOR`, weight cache path, OTLP endpoint, Kafka bootstrap, Postgres URL, Redis URL. <!-- 50ade89 -->
- [X] T019 [P] Create `infra/compose/init-kafka-topics.sh` invoked by an init container that creates topics `diagnostic-findings.v1`, `vehicle-telemetry.v1`, `policy-deployments.v1`, `policy-outcomes.v1`. <!-- 50ade89 -->

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before any user story can begin: VSS vocabulary, weight manifest, database schema and migrations, OAuth2 verification, OTel scaffolding, error model, alert/runbook plumbing, contracts copied into repo root.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T020 [P] Create `scripts/fetch_vss_v6.0.py` that downloads VSS v6.0 at commit SHA `20c609bf95c73b51d483fb8f81a099d1d5b73066`, derives a flat lookup, writes `config/vss/v6.0/signals.yaml`, and writes `config/vss/v6.0/manifest.sha256` (per ADR-0001). <!-- 50ade89 -->
- [X] T021 [P] Create `config/vss/v6.0/pii_signals.yaml` with the PII-adjacent VSS branches (precise geolocation, driver biometrics, personal usage patterns) per Spec Assumptions and Constitution Principle X. <!-- 50ade89 -->
- [X] T022 [P] Create `scripts/fetch_qwen2.5_weights.py` that downloads `Qwen/Qwen2.5-7B-Instruct` at revision SHA `a09a35458c702b33eeacc393d103063234e8bc28`, verifies SHA-256 against `config/slm/qwen2.5-7b-instruct/manifest.sha256` (committed by this task), and stages weights into the local cache. <!-- 50ade89 -->
- [X] T023 [P] Create `scripts/build_qwen_gguf.py` that produces the GGUF Q4_K_M artifact for the CPU profile from the same revision SHA and records its SHA-256 in the same manifest. <!-- 50ade89 -->
- [X] T024 Create `src/collectmind/registry/migrations/` with `alembic.ini` and the migration framework configured against `postgres-timescale`. <!-- 50ade89 -->
- [X] T025 [P] Migration `001_init_tenants.sql`: `tenants` table per `data-model.md`; seed `feature-001-default` tenant. <!-- 50ade89 -->
- [X] T026 [P] Migration `002_diagnostic_findings.sql`: `diagnostic_findings` table; PK `(tenant_id, finding_id)`; indexes per `data-model.md`. <!-- 50ade89 -->
- [X] T027 [P] Migration `003_vehicle_groups.sql`: `vehicle_groups` table; PK `(tenant_id, group_id)`. <!-- 50ade89 -->
- [X] T028 [P] Migration `004_collection_policies.sql`: immutable `collection_policies` table; PK `(tenant_id, policy_id, version)`; trigger that rejects `UPDATE` and `DELETE` outside the erasure path; GIN indexes on `signal_spec` and `trigger_conditions`. <!-- 50ade89 -->
- [X] T029 [P] Migration `005_deployment_targets.sql`: `deployment_targets` table; indexes for the feedback-loop scheduler `(status, expires_at)`. <!-- 50ade89 -->
- [X] T030 [P] Migration `006_policy_outcomes.sql`: `policy_outcomes` table; indexes per `data-model.md`. <!-- 50ade89 -->
- [X] T031 [P] Migration `007_audit_events.sql`: immutable `audit_events` table per `data-model.md`; trigger rejects `UPDATE` and `DELETE`; index on `(correlation_id)`. <!-- 50ade89 -->
- [X] T032 [P] Migration `008_telemetry_observations.sql`: TimescaleDB `telemetry_observations` hypertable; daily chunking; 90-day retention policy. <!-- 50ade89 -->
- [X] T033 [P] Migration `009_erasure_requests.sql`: `erasure_requests` table per `data-model.md`. <!-- 50ade89 -->
- [X] T034 [P] Migration `010_row_level_security.sql`: enable RLS on all tenant-scoped tables; permissive policy in feature 001 (tightened to restrictive in feature 002). <!-- 50ade89 -->
- [X] T035 Create `src/collectmind/observability/otel.py` (OpenTelemetry SDK init, OTLP exporter, RED instrumentation), `src/collectmind/observability/logging.py` (structlog JSON config with PII-stripping rule), and `src/collectmind/observability/metrics.py` (named counters/histograms from FR-014 plus SLM-specific metrics from Constitution). <!-- 50ade89 -->
- [X] T037 [P] Create `src/collectmind/auth/jwt_verifier.py`: PyJWT with cached JWKS (5 min TTL, forced refresh on signature failure), `exp` enforcement, mandatory non-empty `tenant_id` claim, structured rejection codes (`AUTH_INVALID_TOKEN`, `AUTH_EXPIRED`, `AUTH_TENANT_MISSING`). <!-- 50ade89 -->
- [X] T038 [P] Create `src/collectmind/auth/dependencies.py`: FastAPI `Depends()` returning a `Principal{tenant_id, sub, correlation_id}` from a verified JWT. <!-- 50ade89 -->
- [X] T039 [P] Create `src/collectmind/errors.py`: `Recoverable`, `Fatal`, `Validation` exception base classes; the structured `Error` response model matching the contracts' `Error` schema; per-error retry posture metadata. <!-- 50ade89 -->
- [X] T040 Create `src/collectmind/registry/db.py`: asyncpg connection pool, RLS context manager that sets `tenant_id` on every transaction. <!-- 50ade89 -->
- [X] T041 [P] Create `src/collectmind/redis/client.py`: redis-py async client wrapper with the key shape `vehicle_id:signal_name` (per Spec Clarifications Q1, tenant prefix added in feature 002). <!-- 50ade89 -->
- [X] T042 [P] Create `src/collectmind/kafka/producer.py` and `src/collectmind/kafka/consumer.py`: aiokafka wrappers with tenant_id and correlation_id headers. <!-- 50ade89 -->
- [X] T043 [P] Create `tests/contract/asyncapi_harness/` Python package: loads each AsyncAPI 3.0 document and asserts message shape conformance against producer/consumer fixtures. <!-- 50ade89 -->
- [X] T044 Copy `specs/001-policy-loop-vertical-slice/contracts/openapi/*.yaml` and `specs/001-policy-loop-vertical-slice/contracts/asyncapi/*.yaml` into `contracts/openapi/` and `contracts/asyncapi/` at repo root. The repo-root `contracts/` is the source of truth for code generation; the spec-dir `contracts/` remains the spec-time artifact. After T044 lands, the spec-dir contracts are frozen for feature 001; future features regenerate the repo-root contracts via spec → repo-root via this same task pattern. <!-- 50ade89 -->
- [X] T045 Create `src/collectmind/app.py`: FastAPI app composition (orchestration router + query router + erasure router + `/health` + `/ready`), OTel middleware, error handler, request-id middleware that surfaces the same `correlation_id` in logs, traces, and audit records. <!-- 50ade89 -->
- [X] T046 [P] Create `src/collectmind/observability/dashboard_provisioner.py` that validates the JSON in `observability/grafana/dashboards/` is well-formed and references only metrics declared in `metrics.py`. <!-- 50ade89 -->
- [X] T047 [P] Create `observability/runbooks/INDEX.md` and one runbook stub per known alert and failure mode: SLM container OOM, SLM weight digest mismatch, vLLM healthcheck failure, CPU-fallback activation, GPU node group capacity exhaustion, Kafka lag, Postgres pool exhaustion, Redis evictions, dead-letter queue non-empty, container OOM, OAuth2 issuer unavailable. <!-- 50ade89 -->

**Checkpoint**: Foundation ready. User-story implementation can begin.

---

## Phase 3: User Story 1 — Operator runs the policy loop end-to-end (Priority: P1) 🎯 MVP

**Goal**: A fleet diagnostic operator publishes a brake-wear diagnostic finding for a small group of vehicles and observes within stated SLOs a generated, validated, versioned, deployed collection policy and, after the simulated collection window closes, an outcome record stating whether the hypothesis was confirmed or ruled out.

**Independent Test**: Submit one valid brake-wear diagnostic finding through the documented event interface and assert that within the latency budget the system writes a policy record, a deployment record, and (after the simulated window closes) an outcome record linked back to the originating finding. Assert all five Acceptance Scenarios under US1 in `spec.md`.

### Tests for User Story 1 (write FIRST, ensure they FAIL before implementation)

- [X] T048 [P] [US1] Contract test for `orchestration-api.v1.yaml` in `tests/contract/test_orchestration_api_contract.py` (schemathesis), exercising 202/400/401/409/422 paths. <!-- 9c4bd7d -->
- [X] T049 [P] [US1] Contract test for `query-api.v1.yaml` in `tests/contract/test_query_api_contract.py` covering all five operations and the 404 path. <!-- 9c4bd7d -->
- [X] T050 [P] [US1] Contract test for `policy-generator-client.v1.yaml` across all three implementations (`VLLMClient`, `LlamaCppClient`, `FingerprintStubClient`) in `tests/contract/test_slm_client_contract.py`. Warm-up runs in a session-scoped fixture; per-test wall budget 60s warm-path only (per FR-022 and ADR-0004). <!-- 9c4bd7d -->
- [X] T051 [P] [US1] Contract test for `collector-ai-client.v1.yaml` in `tests/contract/test_collector_ai_client_contract.py` against both `SimulatorCollectorAIClient` and the `RealCollectorAIClient` stub. <!-- 9c4bd7d -->
- [X] T052 [P] [US1] AsyncAPI contract tests for the four topics in `tests/contract/test_asyncapi_topics.py` using the harness from T043. <!-- 9c4bd7d -->
- [X] T053 [P] [US1] Unit tests: VSS validator (valid name, invalid name with closest-suggestion, PII-adjacent without consent) in `tests/unit/test_vss_validator.py`. Use hypothesis for property-based tests on signal-name validation. <!-- 9c4bd7d -->
- [X] T054 [P] [US1] Unit tests: `CollectionPolicySpec` Pydantic v2 model invariants (window ≤168h, required fields, semver patterns) in `tests/unit/test_models.py`. <!-- 9c4bd7d -->
- [X] T055 [P] [US1] Unit tests: `PolicyGenerationSession` state object serialization round-trip in `tests/unit/test_session.py`. <!-- 9c4bd7d -->
- [X] T056 [P] [US1] Unit tests: brake-wear hypothesis evaluation rule (confirmed / ruled-out / no-data outcomes) in `tests/unit/test_hypothesis_rule.py`. <!-- 9c4bd7d -->
- [X] T057 [P] [US1] Unit tests: payload signing and verification in `tests/unit/test_signing.py`. <!-- 9c4bd7d -->
- [X] T058 [P] [US1] Unit tests: `schema_version` enforcement (supported major, additive minor/patch tolerated, unknown major rejected) in `tests/unit/test_schema_version.py`. <!-- 9c4bd7d -->
- [X] T059 [P] [US1] Unit tests: composite-key idempotency on duplicate findings in `tests/unit/test_idempotency_unit.py`. <!-- 9c4bd7d -->
- [X] T060 [US1] Integration test: end-to-end finding → policy → deployment → outcome via the real local Compose stack with the real SLM (CPU profile in CI) in `tests/integration/test_e2e_finding_to_outcome.py`. Asserts every Acceptance Scenario 1 and 5 of US1. <!-- 9c4bd7d -->
- [X] T061 [US1] Integration test: VSS-invalid signal rejection (Acceptance Scenario 2 of US1) in `tests/integration/test_vss_rejection.py`. <!-- 9c4bd7d -->
- [X] T062 [US1] Integration test: outcome states (`confirmed`, `ruled_out`, `no_data`) covering Acceptance Scenarios 3 and 4 in `tests/integration/test_outcome_states.py`. <!-- 9c4bd7d -->
- [X] T063 [US1] Integration test: idempotent duplicate finding produces a single policy version and deployment record in `tests/integration/test_idempotency_integration.py`. <!-- 9c4bd7d -->
- [X] T064 [US1] Integration test: GDPR/CCPA right-to-erasure dispatcher propagates to registry, telemetry, audit within the documented bound in `tests/integration/test_erasure.py` (per FR-020a). <!-- 9c4bd7d -->

### Implementation for User Story 1

- [X] T065 [P] [US1] Create `src/collectmind/models/finding.py` (`DiagnosticFinding` Pydantic v2 model matching `data-model.md` and `contracts/asyncapi/diagnostic-findings.v1.yaml`). <!-- b9fddc8 -->
- [X] T066 [P] [US1] Create `src/collectmind/models/policy.py` (`CollectionPolicySpec`, `SignalCollectionSpec`, `TriggerSpec`, `DataGovernanceFlags`). <!-- b9fddc8 -->
- [X] T067 [P] [US1] Create `src/collectmind/models/deployment.py` (`DeploymentRecord`). <!-- b9fddc8 -->
- [X] T068 [P] [US1] Create `src/collectmind/models/outcome.py` (`PolicyOutcome` with the three-state enum). <!-- b9fddc8 -->
- [X] T069 [P] [US1] Create `src/collectmind/models/audit.py` (`AuditEvent` matching `data-model.md` and the audit-record minimum field set in FR-017a). <!-- b9fddc8 -->
- [X] T070 [P] [US1] Create `src/collectmind/models/erasure.py` (`ErasureRequest`, `ErasureReceipt`, per-store status). <!-- b9fddc8 -->
- [X] T071 [P] [US1] Create `src/collectmind/validator/vss.py`: VSS lookup loader (reads `config/vss/v6.0/signals.yaml`), validator with closest-name suggestion via Levenshtein. <!-- b9fddc8 -->
- [X] T072 [P] [US1] Create `src/collectmind/validator/governance.py`: PII-adjacent check using `config/vss/v6.0/pii_signals.yaml`, consent-flag enforcement. <!-- b9fddc8 -->
- [X] T073 [US1] Create `src/collectmind/validator/policy_validator.py`: orchestrates VSS + governance + window bound (≤168h) + signature verification; returns a structured `ValidationResult` with per-error codes (depends on T071, T072). <!-- b9fddc8 -->
- [X] T074 [P] [US1] Create `src/collectmind/slm/client.py`: `PolicyGeneratorClient` Protocol matching `policy-generator-client.v1.yaml`; the `RuntimeInfo` dataclass. <!-- b9fddc8 -->
- [X] T075 [US1] Create `src/collectmind/slm/vllm_client.py`: `VLLMClient` adapter wrapping vLLM's OpenAI-compatible `/v1/chat/completions` and `/v1/completions`, sending `extra_body.guided_json` from `CollectionPolicySpec.model_json_schema()`, asserting deterministic-decoding parameters at startup, recording `RuntimeInfo` (per R-021). <!-- b9fddc8 -->
- [X] T076 [US1] Create `src/collectmind/slm/llamacpp_client.py`: `LlamaCppClient` adapter wrapping `llama-cpp-python` server's OpenAI-compatible surface with the same `outlines` schema binding (per R-021). <!-- b9fddc8 -->
- [X] T077 [US1] Create `src/collectmind/slm/stub_client.py`: `FingerprintStubClient` per ADR-0004; SHA-256 fingerprint over canonical-JSON of (`prompt_template_version`, decoding params, schema, prompt); reads `tests/fixtures/policy_corpus/<fp>/` and returns the recorded output; raises `MissingFingerprint` on miss. <!-- b9fddc8 -->
- [X] T078 [P] [US1] Create `prompts/policy_generator/v1.0.0/system.md` and `prompts/policy_generator/v1.0.0/user.md` with VSS examples for brake-wear hypotheses, documented sampling-rate constraints, and explicit instructions for the `data_governance_flags` fields. <!-- b9fddc8 -->
- [X] T079 [US1] Create `src/collectmind/graph/session.py`: serializable `PolicyGenerationSession` state object with all fields needed for audit lineage (depends on T065–T070). <!-- b9fddc8 -->
- [X] T080 [P] [US1] Create `src/collectmind/graph/orchestrator.py`: Orchestrator node that reads the diagnostic input, writes the execution plan to state, routes on validation outcome, and enforces the bounded retry budget with dead-letter routing (Principle XII). <!-- b9fddc8 -->
- [X] T081 [P] [US1] Create `src/collectmind/graph/policy_generator.py`: Policy Generator node that calls the injected `PolicyGeneratorClient` and writes generated policy to state. <!-- b9fddc8 -->
- [X] T082 [P] [US1] Create `src/collectmind/graph/policy_validator.py`: Policy Validator node that invokes `policy_validator.validate(...)` and on failure injects the structured errors into the retry context for the Generator. <!-- b9fddc8 -->
- [X] T083 [P] [US1] Create `src/collectmind/graph/policy_deployer.py`: Policy Deployer node that writes the immutable policy registry row, calls the injected `CollectorAIClient`, writes the `deployment_targets` row (depends on T067, T085). <!-- b9fddc8 -->
- [X] T084 [US1] Create `src/collectmind/graph/build.py`: LangGraph composition wiring the four nodes with conditional routing on validation outcome (depends on T079–T083). <!-- b9fddc8 -->
- [X] T085 [P] [US1] Create `src/collectmind/registry/repository.py`: immutable `collection_policies`, `deployment_targets`, `policy_outcomes` repos with SQLAlchemy Core / asyncpg. <!-- b9fddc8 -->
- [X] T086 [P] [US1] Create `src/collectmind/registry/audit.py`: `AuditEventWriter` enforcing the FR-017a minimum field set; writes are idempotent on `correlation_id`+`kind`. <!-- b9fddc8 -->
- [X] T087 [P] [US1] Create `src/collectmind/deployer/client.py`: `CollectorAIClient` Protocol matching `collector-ai-client.v1.yaml`. <!-- b9fddc8 -->
- [X] T088 [US1] Create `src/collectmind/deployer/simulator.py`: `SimulatorCollectorAIClient` with configurable failure injection (controlled by an env var or per-request header in tests). <!-- b9fddc8 -->
- [X] T089 [US1] Create `src/collectmind/deployer/real_stub.py`: `RealCollectorAIClient` raising `NotImplementedError` with code `NOT_IMPLEMENTED` unless explicitly enabled by config. <!-- b9fddc8 -->
- [X] T090 [US1] Create `src/collectmind/deployer/signing.py`: canonical-form serialization, signing via `cryptography` (Ed25519 by default), local-key in dev and KMS-backed in cloud, per R-018. <!-- b9fddc8 -->
- [X] T091 [P] [US1] Create `src/collectmind/feedback/scheduler.py`: logical-time scheduler with environment-scoped time-acceleration factor (per FR-009a). <!-- b9fddc8 -->
- [X] T092 [P] [US1] Create `src/collectmind/feedback/evaluator.py`: brake-wear hypothesis evaluator producing `confirmed`/`ruled_out`/`no_data` (depends on T056 unit tests). <!-- b9fddc8 -->
- [X] T093 [US1] Create `src/collectmind/feedback/worker.py`: background worker that polls `deployment_targets WHERE status='accepted' AND expires_at <= now()` and runs the evaluator + outcome writer (depends on T091, T092, T085). <!-- b9fddc8 -->
- [X] T094 [US1] Create `src/collectmind/ingest/http.py`: `POST /findings` handler — auth (T037, T038), schema validation, `schema_version` major check (T087), idempotency (T086), enqueue to `diagnostic-findings.v1` Kafka topic. <!-- b9fddc8 -->
- [X] T095 [P] [US1] Create `src/collectmind/ingest/idempotency.py`: composite-key idempotency check against `diagnostic_findings`. <!-- b9fddc8 -->
- [X] T096 [P] [US1] Create `src/collectmind/ingest/schema_version.py`: major-version supported check; tolerate additive minor/patch (per FR-003a). <!-- b9fddc8 -->
- [X] T097 [US1] Create `src/collectmind/ingest/kafka_consumer.py`: consumes `diagnostic-findings.v1`, invokes the LangGraph from T084, emits `policy-deployments.v1` on success. <!-- b9fddc8 -->
- [X] T098 [P] [US1] Create `src/collectmind/query/api.py`: implementations of `getPolicyById`, `listPolicyVersions`, `getActivePolicyForGroup`, `getOutcomeForFinding`, `getAuditTrail` per `query-api.v1.yaml`. <!-- b9fddc8 -->
- [X] T099 [P] [US1] Create `src/collectmind/erasure/api.py`: `POST /erasure-requests` handler (writes the `erasure_requests` row; returns the receipt with `target_completion_at`). <!-- b9fddc8 -->
- [X] T100 [US1] Create `src/collectmind/erasure/dispatcher.py`: per-store erasure dispatch (registry, telemetry, audit), respecting the 30-day default bound; produces per-store status; distinguishes `erased` and `redacted` (per FR-020a, R-017). <!-- b9fddc8 -->
- [X] T101 [P] [US1] Create `src/collectmind/simulators/diagnostic_finding_generator.py`: synthetic upstream that emits brake-wear findings with controllable parameters. <!-- b9fddc8 -->
- [X] T102 [P] [US1] Create `src/collectmind/simulators/telemetry_generator.py`: synthetic post-collection telemetry parameterized by deployed policy. <!-- b9fddc8 -->
- [X] T103 [P] [US1] Create `tests/fixtures/policy_corpus/<fingerprint-1>/{input.json,output.json,usage.json,metadata.json}`: initial PR-tier corpus entry recorded against the real SLM (one fingerprint). <!-- b9fddc8 -->
- [X] T104 [US1] Wire the FastAPI app in `src/collectmind/app.py`: routers from T094, T098, T099; error handler that emits the structured `Error` shape and never echoes payloads on auth failure; OTel middleware; readiness probe that polls the SLM `/info` endpoint and verifies the weight SHA against the manifest. <!-- b9fddc8 -->

**Checkpoint**: At this point, User Story 1 is fully functional. The end-to-end finding-to-outcome integration test (T060) and the four contract tests (T048–T051) all pass against the real local stack.

---

## Phase 4: User Story 2 — On-call observes pipeline, paged on breach (Priority: P2)

**Goal**: An on-call engineer opens one operational dashboard and sees the live state of the pipeline and is paged on SLO breach with a runbook link.

**Independent Test**: Inject a sustained burst of findings exceeding a configured rate, observe the dashboard populate within seconds, verify an alert fires when the latency budget is breached, and confirm the alert links to a documented runbook page. Assert every Acceptance Scenario under US2 in `spec.md`.

### Tests for User Story 2

- [X] T105 [P] [US2] Contract test: `observability/grafana/dashboards/collectmind-end-to-end.json` parses, references only declared metrics, and contains the panels mandated by FR-014/FR-015 in `tests/contract/test_dashboard_provisioning.py`. <!-- 3266b13 -->
- [X] T106 [P] [US2] Unit test: every alert rule in `observability/prometheus/rules.yaml` has a corresponding runbook entry under `observability/runbooks/` in `tests/unit/test_alert_runbook_parity.py` (asserts FR-022 CI guard's behavior). <!-- 3266b13 -->
- [X] T107 [US2] Integration test: SLO breach simulation triggers alert; Alertmanager webhook payload contains the runbook URL in `tests/integration/test_slo_alert.py`. <!-- 3266b13 -->
- [X] T108 [US2] Integration test: dashboard reflects pipeline state with at most 10s of lag from event acceptance, asserting SC-006 in `tests/integration/test_dashboard_lag.py`. <!-- 3266b13 -->
- [X] T109 [US2] Integration test: 1-minute internal-dependency outage; queued events drain within 5 minutes of recovery; no event lost — exercises FR-022a in `tests/integration/test_recovery_from_outage.py`. <!-- 3266b13 -->

### Implementation for User Story 2

- [X] T110 [US2] Create `observability/grafana/dashboards/collectmind-end-to-end.json` with panels: ingest rate, generation funnel (received → generated → validated → deployed → confirmed/ruled_out/no_data), validation pass rate, time-to-deploy histogram (p50/p95/p99), hypothesis confirmation rate, dead-letter count, retry rate, SLM latency, SLM constraint-violation rate, active SLM weight SHA, active runtime image digest, authentication-failure rate. <!-- d80fc84 -->
- [X] T111 [P] [US2] Create `observability/prometheus/rules.yaml` with one alert per binding SLO: SC-001 (latency p95), SC-002 (success-rate breach), SC-003 (soak error-rate / memory-growth), SC-004 (query p95), SC-005 (recovery time exceeded), SC-006 (dashboard lag), SC-010 (outcome write delay), SC-012 (availability). <!-- d80fc84 -->
- [X] T112 [P] [US2] Author the per-alert runbook pages under `observability/runbooks/` (one page per alert from T111 plus the failure-mode pages from T047): symptoms, dashboard links, mitigation steps, escalation, related ADRs. <!-- d80fc84 -->
- [X] T113 [US2] Create `scripts/check_runbook_completeness.py`: invoked in CI, parses `observability/prometheus/rules.yaml` and `observability/runbooks/`, fails the build if any alert lacks a runbook entry (FR-022 + R-019). <!-- d80fc84 -->
- [X] T114 [P] [US2] Add metrics emission in `src/collectmind/observability/metrics.py` for every metric panel from T110, with histogram buckets sized for the SLO assertions in T111. <!-- d80fc84 -->
- [X] T115 [US2] Create Alertmanager configuration in `infra/compose/alertmanager.yaml` that routes alerts to a local webhook receiver (`scripts/local_webhook.py`) for integration-test consumption; cloud routing is config-only and pinned in plan. <!-- d80fc84 -->

**Checkpoint**: User Story 2 is fully functional. The dashboard is provisioned automatically by the local stack; alerts fire on SLO breach; every alert has a runbook link.

---

## Phase 5: User Story 3 — Reviewer trusts the system to merge changes safely (Priority: P3)

**Goal**: A reviewer opens the project and sees passing automated tests in CI, a one-command quickstart, security gates, an SBOM, and documentation a stranger could follow.

**Independent Test**: Clone repo to a fresh machine, run the documented quickstart command, observe stack come up under 10 minutes, run the documented test command, observe every test tier pass; CI on a representative PR is green within 20 minutes.

### Tests for User Story 3

- [X] T116 [P] [US3] Smoke load: `tests/load/locustfile_smoke.py` runs against the deterministic-fingerprint stub for 60s at 10% of N2 and asserts no errors and median latency under the smoke threshold. <!-- fe9eb41 -->
- [X] T117 [P] [US3] Full-profile load: `tests/load/locustfile_full.py` runs against the real SLM at SC-002's profile (1,000 events/s/tenant for 30 min) and asserts SC-002. <!-- fe9eb41 -->
- [X] T118 [P] [US3] Soak: `tests/load/locustfile_soak.py` runs at 50% of N2 for 24h on the self-hosted GPU runner and asserts SC-003 (memory growth ≤5%, error rate ≤0.1%). <!-- fe9eb41 -->

### Implementation for User Story 3

- [X] T119 [US3] Create `.github/workflows/ci.yaml` (PR tier): `ruff check`, `ruff-format --check`, `mypy --strict`, `pytest tests/unit`, `pytest tests/contract` (incl. real-SLM contract test under the 60s warm-path budget), `pytest tests/integration` (real local stack via testcontainers), Buildx container build, Trivy scan (fail on critical/high), Syft SBOM, Bandit, Semgrep, pip-audit, gitleaks, `make load-smoke`, `terraform fmt -check`, `terraform validate`, `tflint`, `terraform plan -workspace=dev`, coverage upload. Jobs are parallelized in the workflow YAML; the 20-minute budget (SC-009) is the wall-clock total, not the sum of job durations. The workflow MUST capture `github.event.pull_request.created_at` to job-end wall-clock and emit it as a CI artifact `ci-wall-clock.json`; a final job in the workflow asserts the value against SC-009 and reports a build warning at >18 min and a build failure at >20 min over a rolling 5-PR window (rolling window prevents flakes from blocking individual PRs). <!-- fe9eb41 -->
- [X] T120 [US3] Create `.github/workflows/ci-workflow-dispatch.yaml`: full-profile Locust against real SLM; broader SLM contract regression against the full corpus; `terraform apply -workspace=dev`; eval suite. Manual trigger only. <!-- fe9eb41 -->
- [X] T121 [US3] Create `.github/workflows/nightly.yaml`: 24-hour soak on the self-hosted GPU runner. Cron entry; tracked in runbook for cadence-relaxation contingency. <!-- fe9eb41 -->
- [X] T122 [US3] Create `.github/workflows/record-corpus.yaml`: workflow_dispatch corpus-recording job per ADR-0004. Authors PRs that add new fingerprints to `tests/fixtures/policy_corpus/`. <!-- fe9eb41 -->
- [X] T123 [P] [US3] Configure Trivy at `.trivyignore` (empty) and add the Trivy build step that runs against the application image and the SLM image; fail on critical/high. <!-- fe9eb41 -->
- [X] T124 [P] [US3] Configure Syft at `.syft.yaml`; the SBOM step uploads the SBOM as a CI artifact and includes the model weight manifest alongside Python deps (per Principle IX). <!-- fe9eb41 -->
- [X] T125 [P] [US3] Create `scripts/check_no_todo_fixme.py`: greps the source tree, fails on `TODO`/`FIXME`/`XXX`/`@todo` (per Principle III). <!-- fe9eb41 -->
- [X] T126 [P] [US3] Create `scripts/check_slm_pinning.py`: reads `infra/compose/docker-compose.yaml` and the SLM Dockerfiles, asserts vLLM image digest, weight SHA, and decoding seed match the manifest in `config/slm/qwen2.5-7b-instruct/manifest.sha256` and ADR-0002 (per Principle XIV). <!-- fe9eb41 -->
- [X] T127 [P] [US3] Create `scripts/check_secrets.py` (gitleaks wrapper) wired into CI and pre-commit. <!-- fe9eb41 -->
- [X] T128 [US3] Create `infra/terraform/networking/main.tf`, `infra/terraform/compute/main.tf` (ECS Fargate for app, ECS-on-EC2 with `g5.2xlarge` Capacity Provider for the SLM, EKS variant under `infra/terraform/eks/`), `infra/terraform/data/main.tf` (RDS Postgres+Timescale, ElastiCache, MSK), `infra/terraform/storage/main.tf` (S3 weight cache), `infra/terraform/secrets/main.tf` (Secrets Manager + IAM least-privilege), `infra/terraform/observability/main.tf` (ADOT collector, CloudWatch wiring) per ADR-0005. <!-- fe9eb41 -->
- [X] T129 [US3] Create `infra/terraform/ci_runner/main.tf`: self-hosted GitHub Actions runner with GPU for the nightly soak. <!-- fe9eb41 -->
- [X] T130 [US3] Update `README.md` to its complete form: pitch, Mermaid arch diagram, quickstart link, badges (CI, coverage), license, link to `/docs`, link to `specs/001-policy-loop-vertical-slice/`. <!-- fe9eb41 -->
- [X] T131 [US3] Author `docs/security/threat-model.md`: STRIDE + LINDDUN coverage; the three threats already named in spec (spoofed tenant claim, replayed event, semantic abuse via schema-conformant payload) plus SLM supply-chain, prompt injection from hypothesis text, and dashboard leakage; map each threat to FRs that handle it (per R-019). <!-- fe9eb41 -->
- [X] T132 [P] [US3] Add a CI step in `ci.yaml` that runs `python -m collectmind.openapi.dump > docs/api/openapi.yaml`, commits-via-bot if changed, and fails the build if drift is detected from the contract source of truth at `contracts/openapi/`. <!-- fe9eb41 -->
- [X] T133 [P] [US3] Author `docs/examples/finding-brake-wear.json` example payload referenced by the quickstart. <!-- fe9eb41 -->

**Checkpoint**: All three user stories independently functional. CI is green. Quickstart runs in under 10 minutes on a clean machine.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories.

- [ ] T134 [P] Coverage sweep: add unit tests where pytest-cov reports below the 85% line floor; ensure CI gate is green at the floor (per Principle IV).
- [ ] T135 [P] Lint and type sweep: run `make lint` and `make typecheck` across the codebase; fix any drift introduced during implementation.
- [ ] T136 [P] Dashboard-lag SLO measurement: confirm SC-006 holds in steady state on the local stack; record the measured value in the runbook.
- [ ] T137 [P] Run `make eval` once US1 is complete; record the eval-suite baseline values from ADR-0002's bracketed table via a follow-up commit titled `docs: ADR-0002 record eval baseline` and promote ADR-0002 from `Proposed` to `Accepted` in the same commit.
- [ ] T138 [P] Cross-link spec/plan/research/data-model/contracts/quickstart from `README.md` and `/docs`.
- [ ] T139 Run `quickstart.md` end-to-end on a clean machine; update the troubleshooting table if any step fails.
- [ ] T140 [P] Verify CLAUDE.md SPECKIT block points at the current plan path (already updated in plan output; this task is the verification).
- [ ] T141 Production-readiness review against the constitution: check every NON-NEGOTIABLE principle (IV, VII, IX, X, XI, XIII, XIV) against the implemented system; record findings in `docs/runbook/feature-001-readiness-review.md`.
- [ ] T142 [P] CI gate for SC-007: create `tests/unit/test_pii_strip.py` and `scripts/check_log_pii.py`. The unit test injects synthetic logs containing PII patterns and asserts the structlog config in `src/collectmind/observability/logging.py` strips them. The script consumes recent CI log artifacts and metric label dumps, scans for PII signatures (geolocation coordinates, biometric tokens, personal identifiers), and fails the build on any hit. Wire the script into `.github/workflows/ci.yaml` so SC-007 is verified by an automated check on every build.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup** — no dependencies; parallel-friendly except T011 (single Compose file).
- **Phase 2 Foundational** — depends on Phase 1; many tasks parallelizable.
- **Phase 3 US1 (P1, MVP)** — depends on Phase 2.
- **Phase 4 US2 (P2)** — depends on Phase 2 (US1 not strictly required, but sharing the metric set from T114 reduces churn).
- **Phase 5 US3 (P3)** — depends on Phase 2 (CI workflow tasks need the test scaffolding from US1 to be meaningful; load tasks T117–T118 logically depend on T060 stability).
- **Phase 6 Polish** — depends on US1, US2, US3.

### User Story Dependencies

- US1 (P1) — independent. Delivers the MVP.
- US2 (P2) — independent of US1 in principle; in practice shares metric definitions T114 with US1. Either can be implemented first; concurrent work is fine if T114 lands early in US1.
- US3 (P3) — independent of US2; shares no implementation paths. CI workflows (T119–T122) integrate the test tasks from US1, US2, and US3 itself.

### Within Each User Story

- Tests (test-first per Principle IV) are written before the implementation tasks in the same story.
- Models before services; services before endpoints; integration tests after endpoints.
- Code-signing (T090) before deployer (T088) so the simulator can verify signatures.
- LangGraph composition (T084) after all four nodes (T080–T083).
- The deterministic stub corpus (T103) records the recorded output AFTER the SLM clients (T075–T077) and the LangGraph composition (T084) are in place; it cannot be authored before then because the recording job runs the real client end-to-end. The end-to-end integration test (T060) depends on T103 because the integration test uses the real SLM in CPU profile and asserts byte-equality against a recorded fingerprint where applicable; the dependency is `T075,T076,T077,T084 → T103 → T060`.

### Parallel Opportunities

- All Phase 1 tasks marked `[P]` are parallel.
- All Phase 2 migration tasks T025–T034 are parallel (different SQL files).
- Within US1, all `models/` files (T065–T070) are parallel; all unit-test files (T053–T059) are parallel; the four LangGraph node files (T080–T083) are parallel.
- US1, US2, and US3 can be staffed in parallel by separate developers once Phase 2 completes; only the metric definitions (T114) are a shared dependency, and they land in US2.

---

## Parallel Example: User Story 1

```bash
# Tests for US1 (parallel):
Task: "Contract test for orchestration-api.v1.yaml in tests/contract/test_orchestration_api_contract.py"
Task: "Contract test for query-api.v1.yaml in tests/contract/test_query_api_contract.py"
Task: "Contract test for policy-generator-client.v1.yaml in tests/contract/test_slm_client_contract.py"
Task: "Contract test for collector-ai-client.v1.yaml in tests/contract/test_collector_ai_client_contract.py"
Task: "AsyncAPI contract tests in tests/contract/test_asyncapi_topics.py"

# Models for US1 (parallel):
Task: "Create DiagnosticFinding model in src/collectmind/models/finding.py"
Task: "Create CollectionPolicySpec model in src/collectmind/models/policy.py"
Task: "Create DeploymentRecord model in src/collectmind/models/deployment.py"
Task: "Create PolicyOutcome model in src/collectmind/models/outcome.py"
Task: "Create AuditEvent model in src/collectmind/models/audit.py"
Task: "Create ErasureRequest model in src/collectmind/models/erasure.py"

# LangGraph nodes for US1 (parallel; build composes them):
Task: "Orchestrator node in src/collectmind/graph/orchestrator.py"
Task: "Policy Generator node in src/collectmind/graph/policy_generator.py"
Task: "Policy Validator node in src/collectmind/graph/policy_validator.py"
Task: "Policy Deployer node in src/collectmind/graph/policy_deployer.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories).
3. Complete Phase 3: User Story 1 (MVP).
4. **STOP and VALIDATE**: T060 integration test green; quickstart end-to-end on a clean machine; dashboard provisioned (a partial T110 is sufficient for the visual smoke test).
5. Demo if ready.

### Incremental Delivery

1. Setup + Foundational → ready.
2. Add US1 → MVP demo.
3. Add US2 → operational dashboards and alerts demo.
4. Add US3 → CI/CD and quickstart demo.
5. Phase 6 polish → production-readiness review.

### Parallel Team Strategy

With multiple developers:

1. Team completes Phase 1 + Phase 2 together.
2. Once Foundational lands:
   - Developer A: US1 (MVP, longest critical path).
   - Developer B: US2 (dashboards, alerts, runbooks).
   - Developer C: US3 (CI/CD, IaC, threat model, README).
3. Stories complete and integrate independently.

---

## Notes

- `[P]` tasks are file-disjoint and dependency-disjoint at the moment they are marked.
- `[Story]` labels map tasks to spec.md user stories for traceability and the V-Model matrix.
- Test-first per Principle IV: write the test, see it fail, then implement.
- Real local stack means `docker compose up` with the real SLM container; no in-memory shims for stores or transports.
- Commit cadence: after each task or each logical group; the no-TODO/FIXME guard runs on every commit via pre-commit.
- Stop at any checkpoint to validate independently.
