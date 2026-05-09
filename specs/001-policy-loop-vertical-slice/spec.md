# Feature Specification: Policy-Loop Vertical Slice

**Feature Branch**: `001-policy-loop-vertical-slice`
**Created**: 2026-05-09
**Status**: Draft
**Input**: User description: "Specify the first feature of CollectMind. The feature is named policy-loop-vertical-slice and its purpose is to deliver an end-to-end vertical slice of the CollectMind value proposition that operators can run, observe, and trust in production. Describe what the system must do and why; do not describe how it is implemented or which technologies it uses."

## Background

CollectMind is an autonomous policy engine that reacts to diagnostic findings about vehicles and decides what additional telemetry should be collected to confirm or rule out a hypothesis. A diagnostic finding describes a single anomaly observed on one or more vehicles in a fleet, the hypothesis being tested, and the candidate signals that would resolve the hypothesis. Today, the work of converting that finding into a deployed collection campaign is manual; this feature replaces that manual step for one well-bounded class of findings.

This first feature is deliberately a vertical slice: it touches every layer of the system from inbound diagnostic event to outcome record, with full observability and gated continuous integration, while keeping breadth narrow (single tenant, single hypothesis class, simulated upstream and downstream). Subsequent features extend the same vertical rather than bolt new layers on the side.

### In scope

- Single tenant. Multi-tenant isolation is a separate feature.
- Single hypothesis class: brake-wear early-stage anomaly. Other anomaly classes are out of scope here.
- Synthetic diagnostic events injected through a documented event interface; the real upstream diagnostic system is out of scope.
- Synthetic post-collection telemetry is acceptable to close the feedback loop within this feature; the real telemetry source is out of scope.
- The downstream collection control plane is treated as an external system with a documented API contract; an in-process simulator stands in for it. Real integration is out of scope.

### Explicitly out of scope

Multi-tenant isolation, ECU capability modeling, retry orchestration on validation failure, human review queue, real upstream diagnostic source, real downstream control plane, per-tenant configuration of confidence thresholds, infrastructure-as-code for cloud deployment.

## Clarifications

### Session 2026-05-09

- Q: Finding identifier uniqueness scope → A: Composite `(tenant_id, finding_id)` per tenant; in feature 001 `tenant_id` defaults to a constant.
- Q: Authentication scheme for inbound events → A: OAuth2 client-credentials grant per tenant; JWT bearer required on every request; `tenant_id` carried as a non-empty JWT claim.
- Q: Inbound event schema versioning posture → A: Every event MUST carry `schema_version`; system supports exactly one major version at a time; unknown additive fields at minor/patch tolerated and ignored; unknown major rejected with structured error.
- Q: Availability SLO target → A: 99.9 percent monthly availability for the inbound and query interfaces (~43 minutes downtime per month); SC-005's recovery-from-outage criterion stands alongside as the acute-event constraint.
- Q: Maximum collection-window length → A: Two-tier. Production maximum 168 hours (7 days). Tests run on a configurable time-acceleration factor that maps the same logical window to seconds of wall-clock. System reads windows in logical time; one factor scales the scheduler's clock.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operator runs the policy loop end-to-end (Priority: P1)

A fleet diagnostic operator publishes a brake-wear diagnostic finding for a small group of vehicles and observes, within stated service-level objectives, a generated, validated, versioned, deployed collection policy and, after the simulated collection window closes, an outcome record stating whether the hypothesis was confirmed or ruled out.

**Why this priority**: This is the entire value proposition of CollectMind. Without this loop, the system has no purpose. Every other story is a supporting concern.

**Independent Test**: Can be fully tested by submitting one valid brake-wear diagnostic finding through the documented event interface and asserting that within the latency budget the system writes a policy record, a deployment record, and (after the simulated window closes) an outcome record linked back to the originating finding.

**Acceptance Scenarios**:

1. **Given** a single brake-wear diagnostic finding for three vehicles, **When** the operator publishes the finding through the inbound event interface, **Then** within the p95 latency budget the system produces a policy record, a deployment record, and (after the simulated collection window) an outcome record, all linked by lineage to the originating finding.
2. **Given** a diagnostic finding whose candidate signals contain a name not in the canonical signal vocabulary, **When** the operator publishes the finding, **Then** the system rejects the resulting policy with a structured error that names every invalid signal, no policy is written to the registry, and no deployment record is produced.
3. **Given** a published finding that produces a deployed policy, **When** the simulated collection window expires and synthetic post-collection telemetry confirms the hypothesis, **Then** the outcome record marks the hypothesis confirmed and references the same lineage as the originating finding.
4. **Given** a published finding that produces a deployed policy, **When** the simulated collection window expires and the synthetic telemetry does not confirm the hypothesis, **Then** the outcome record marks the hypothesis ruled out and references the same lineage.
5. **Given** a registry containing several versions of policies generated from related findings, **When** the operator queries the registry by vehicle group, finding identifier, or policy identifier, **Then** the system returns the active version, the full version history, and the linked outcome records within the read-latency budget.

---

### User Story 2 - On-call engineer observes the pipeline and is paged on breach (Priority: P2)

An on-call engineer opens one operational dashboard and sees the live state of the pipeline: incoming findings, generated policies, validation pass rate, deployments, and outcomes. When the pipeline breaches a service-level objective, the on-call engineer is paged with a link to the runbook entry that explains the failure.

**Why this priority**: A system that cannot be operated cannot be trusted in production, regardless of how good its happy path is. This story makes the operational surface real on day one rather than deferred.

**Independent Test**: Can be tested by injecting a sustained burst of findings that exceeds a configured rate, observing the dashboard populate within seconds, and verifying that an alert fires when the latency budget is breached and that the alert links to a documented runbook page.

**Acceptance Scenarios**:

1. **Given** the system is running idle, **When** the operator publishes a finding, **Then** the dashboard shows the finding flowing through ingest, generation, validation, deployment, and outcome with at most 10 seconds of lag from event acceptance.
2. **Given** a sustained ingest rate above the configured threshold, **When** an end-to-end latency breach occurs, **Then** an alert fires within one minute, names the breached metric, and links to the runbook page that describes the failure and the recovery procedure.
3. **Given** the dashboard is open, **When** any operation produces a structured log, **Then** that log is correlated to the originating finding by a single shared identifier visible in the dashboard.
4. **Given** an internal dependency outage of up to one minute, **When** the dependency recovers, **Then** the dashboard shows queued events draining within five minutes and no event is lost.

---

### User Story 3 - Reviewer trusts the system to merge changes safely (Priority: P3)

A code reviewer opens the project repository and sees passing automated tests in continuous integration. The full test suite runs locally with one command. The full stack runs locally with one command. A security reviewer can see authentication on every endpoint that is not health or readiness, no secrets in the repository, pinned dependencies, vulnerability scans, and a software bill of materials emitted on every build. A new engineer who has never seen the project can ship a small, correct change in under one working day.

**Why this priority**: Without this story, the operator value of P1 and P2 is not durable: changes will introduce regressions, security drift will accumulate, and the project will become unrecognizable within months. This story makes the maintenance surface real on day one.

**Independent Test**: Can be tested by cloning the repository to a fresh machine, running the documented quickstart command, observing the stack come up in under ten minutes, running the documented test command, observing every test tier pass, and reading the documented runbook and architecture overview to confirm a stranger could ship a change.

**Acceptance Scenarios**:

1. **Given** a fresh clone of the repository, **When** a reviewer runs the quickstart command, **Then** the entire stack is running and reachable through documented local endpoints in under ten minutes.
2. **Given** a fresh clone of the repository, **When** a reviewer runs the documented test command, **Then** every test tier (unit, contract, integration, smoke load) executes and reports a pass-or-fail outcome with no manual setup steps.
3. **Given** a pull request that breaks any acceptance scenario in this specification, **When** the pull request is opened, **Then** continuous integration reports a failing check that names the broken scenario and blocks the merge.
4. **Given** a pull request that introduces a hard-coded secret, **When** the pull request is opened, **Then** continuous integration reports a failing check that names the secret detection, and the pull request cannot be merged.
5. **Given** a pull request that adds a new dependency, **When** the build runs, **Then** a software bill of materials is emitted and a vulnerability scan reports critical and high findings as a build artifact; merge is blocked on critical or high findings.

---

### Edge Cases

- A diagnostic finding arrives whose hypothesis is outside the brake-wear class supported by this feature: the system rejects the finding with a structured error and does not generate a policy.
- A diagnostic finding arrives that fails authentication: the system rejects the finding with an authentication error, never inspects the payload, and increments an authentication-failure metric.
- A diagnostic finding arrives whose payload does not conform to the documented event schema: the system rejects the finding with a structured schema error and does not enqueue it for processing.
- A generated policy targets vehicles for which the simulated collection produces no telemetry by the time the window expires: the outcome record is written with status "no data," not silently dropped.
- The simulated downstream control plane is configured to inject failures: the system handles each failure as a deployment fault, logs it, surfaces it in the dashboard, and does not silently mark the policy as deployed.
- The same finding identifier is published twice in close succession: the system idempotently produces a single policy version and a single deployment record.
- The dashboard is opened while no findings have ever been published: the dashboard renders, all panels report zero, and no panel shows an error.
- The operator queries the registry for an unknown identifier: the system returns a structured "not found" response, not an empty success.

## Requirements *(mandatory)*

### Functional Requirements

#### Inbound and validation

- **FR-001**: The system MUST accept a diagnostic finding event that conforms to a documented event schema. The schema MUST include vehicle scope, anomaly type, hypothesis statement, candidate signals, and a confidence score from the upstream source.
- **FR-002**: The system MUST reject any inbound event that does not carry a valid JWT bearer token issued under the configured OAuth2 client-credentials grant, and MUST reject any token whose `tenant_id` claim is missing or empty. The `tenant_id` claim from the validated token populates the composite finding key.
- **FR-002a**: The system MUST reject any inbound JWT whose `exp` (expiration) claim is in the past with a structured error and MUST NOT inspect or process the payload. The OAuth2 issuer URL, JWKS endpoint location, and signing-key rotation cadence are pinned in the plan; the spec does not commit to specific values.
- **FR-003**: The system MUST reject any inbound event whose payload does not conform to the documented event schema, with a structured error that names the failing field.
- **FR-003a**: Every inbound event MUST carry a `schema_version` field. The system supports exactly one major version at a time; minor or patch additive fields the system does not recognize MUST be tolerated and ignored. Any event whose `schema_version` declares an unsupported major version MUST be rejected with a structured error that names the supported major version.

#### Policy generation and validation

- **FR-004**: For an accepted finding, the system MUST generate a collection policy that selects signals appropriate to the hypothesis, sets sampling rates and trigger conditions, and bounds the collection to a time window. The generated policy MUST conform to a documented policy schema.
- **FR-005**: The system MUST validate every signal name in the generated policy against the canonical vehicle signal vocabulary.
- **FR-006**: The system MUST reject any policy that contains a signal name not in the canonical vocabulary, returning a structured error that names every invalid signal.

#### Registry and deployment

- **FR-007**: The system MUST write every validated policy as an immutable record in a registry. Each record MUST carry a semantic version, a lineage link to the originating finding, the deployment scope, and the time of creation. Records MUST NOT be modifiable after they are written.
- **FR-008**: The system MUST deliver the validated policy to the documented downstream collection control plane interface and produce a deployment record that links the policy version to the deployed scope.

#### Feedback loop

- **FR-009**: After the policy's collection window closes, the system MUST evaluate the resulting telemetry against the original hypothesis and write an outcome record (confirmed, ruled out, or no data) that links to the originating finding.
- **FR-009a**: Collection windows MUST be expressed in logical time; the system MUST reject any policy whose requested window exceeds 168 hours of logical time. The scheduler's wall-clock advancement MUST be controlled by a single environment-scoped time-acceleration factor so that production and test environments traverse the same code path at different speeds and produce equivalent outcome records.

#### Query

- **FR-010**: The system MUST expose a query interface that returns: a policy by identifier, the active policy for a vehicle group, the version history of a policy, the deployment record for a policy version, and the outcome record for a finding.
- **FR-011**: The system MUST return a structured "not found" response for unknown identifiers; it MUST NOT return an empty success.

#### Idempotency and concurrency

- **FR-012**: The system MUST treat duplicate publications of the same `(tenant_id, finding_id)` composite key as idempotent and produce a single policy version and a single deployment record.

#### Observability and operations

- **FR-013**: The system MUST emit structured logs for every accepted, rejected, generated, validated, deployed, and outcome operation, each correlated to a shared identifier traceable across the pipeline. Every log entry and every audit record produced from an inbound event MUST include the inbound `schema_version` so a reviewer can correlate a malformed event with the schema it claims.
- **FR-014**: The system MUST emit metrics for at minimum: ingest rate, generation funnel (received, generated, validated, deployed, confirmed, ruled-out, no-data), validation pass rate, end-to-end time-to-deploy distribution, hypothesis confirmation rate, dead-letter count, and authentication-failure count.
- **FR-015**: The system MUST expose a single operator dashboard that surfaces the metrics from FR-014 with at most 10 seconds of lag from event acceptance.
- **FR-016**: The system MUST raise an alert when any service-level objective from the Success Criteria is breached, and the alert MUST name the breached metric and link to a documented runbook entry.
- **FR-017**: The system MUST exclude personal data and raw signal payloads above a configured size from logs, traces, and metric labels.
- **FR-017a**: Every audit record produced by the policy-generation pipeline MUST carry the following minimum field set: composite finding identifier (`tenant_id`, `finding_id`), SLM repository and revision SHA, prompt template version, decoding seed, policy identifier and version, deployment record reference, and (when the feedback loop has run) the outcome record reference.

#### Security and supply chain

- **FR-018**: The system MUST require authentication on every external endpoint except documented health and readiness endpoints.
- **FR-019**: The repository MUST not contain secrets, and continuous integration MUST verify their absence on every change.
- **FR-020**: Continuous integration MUST emit a software bill of materials and run vulnerability scanning for every build, MUST block merges on critical or high findings, and MUST gate merges on the failure of any test tier.
- **FR-020a**: The system MUST implement GDPR and CCPA right-to-erasure paths that propagate a deletion request from the inbound query interface to every store that can hold subject data: the policy registry, the telemetry store, and the audit log. Each erasure request MUST complete within a documented bound (the bound is pinned in the plan and exposed in the runbook), MUST itself produce an audit record, and MUST distinguish "erased" from "redacted to preserve referential integrity" in the response.

#### Quality gates

- **FR-021**: The system MUST ship with automated tests in continuous integration that exercise every functional requirement above: unit tests for internal logic, contract tests for every external surface, an integration test for the end-to-end finding-to-outcome path against the real local stack, and a load test that asserts the service-level objectives in the Success Criteria.
- **FR-022**: The system MUST ship with a runbook entry for every alert it can raise. Continuous integration MUST fail the build if any alert rule defined in the repository lacks a corresponding runbook entry, verified by an automated check. The PR-tier `PolicyGeneratorClient` contract test against the real SLM MUST budget no more than 60 seconds of warm-path wall time for its assertion phase; cold start (image pull, weight load, FSM compilation) MUST be excluded from that budget and bounded separately by the readiness-probe timeout, with the warm-up performed by a session-scoped fixture before any assertion runs.
- **FR-022a**: SC-005's recovery-from-outage criterion MUST be exercised by an integration test that simulates a controllable internal-dependency outage of bounded duration and asserts that queued events drain within five minutes of recovery and no event is lost.

### Key Entities

- **Diagnostic finding**: A structured statement that a vehicle group exhibits an anomaly of a known type, the hypothesis being tested, the candidate signals that would resolve the hypothesis, and an upstream confidence score. The unit of input.
- **Collection policy**: A versioned, immutable specification of which signals to collect, at what rate, under what trigger, for which vehicles, and for how long. Generated from a finding; the unit of work the system produces.
- **Policy version**: A specific immutable revision of a collection policy. Each policy may have many versions; only one is active per scope at a time.
- **Deployment record**: A record that a specific policy version was delivered to a specific scope at a specific time, with a status of accepted or rejected by the downstream control plane.
- **Telemetry observation**: A simulated post-collection signal reading attributed to a vehicle and a policy version, used by the feedback loop to evaluate the hypothesis.
- **Outcome record**: A record that links back to the originating finding and states whether the hypothesis was confirmed, ruled out, or could not be evaluated for lack of data.
- **Vehicle group**: A bounded set of vehicle identifiers that a policy targets.
- **Hypothesis**: The proposition that a finding is testing, expressed in plain language, with a class label that this feature recognizes ("brake-wear early-stage").

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From the moment an authenticated diagnostic event is accepted to the moment its policy is recorded as deployed: p50 at most 4 seconds, p95 at most 12 seconds, p99 at most 30 seconds, measured under the load profile in SC-002.
- **SC-002**: The system sustains an inbound rate of at least 1,000 diagnostic events per second for at least 30 minutes with end-to-end success rate at or above 99.9 percent (measured by the full-profile load suite, run on workflow_dispatch and on the schedule recorded in the runbook (per Principle XIV)).
- **SC-003**: The system runs at 50 percent of the SC-002 peak rate for at least 24 hours with no resident-memory growth above 5 percent and an error rate at most 0.1 percent (measured by the full-profile load suite, run on workflow_dispatch and on the schedule recorded in the runbook (per Principle XIV)).
- **SC-004**: The query interface for retrieving a policy, its version history, or its outcome record returns within p95 200 milliseconds at a sustained read rate of 100 reads per second.
- **SC-005**: After a one-minute outage of any single internal dependency, queued events drain within five minutes of recovery and no event is lost.
- **SC-006**: The operator dashboard reflects every metric in FR-014 with at most 10 seconds of lag from event acceptance.
- **SC-007**: No personal data or secret material appears in any log line, trace span, or metric label produced by the system, verified by an automated check that runs on every build.
- **SC-008**: A reviewer can stand up the entire stack on a clean machine and run the documented quickstart in under 10 minutes.
- **SC-009**: A pull request from a reviewer who has never seen the project can pass continuous integration and merge in under 20 minutes of cumulative pipeline time, end to end, on average. The 20-minute target applies to the PR-tier pipeline only (lint, type-check, unit, contract, integration with real local stack, smoke load on deterministic-fingerprint stub, security scans, SBOM, container build). Workflow-dispatch tiers (full SLM eval, full-profile load, soak) are not measured by this criterion.
- **SC-010**: For a deployed policy whose simulated post-collection telemetry confirms the hypothesis, the outcome record is written within five minutes of the collection window closing.
- **SC-011**: Under deterministic decoding against the contract-test corpus, every generated policy is schema-valid and uses only canonical signal names. Schema violations are zero.
- **SC-012**: The inbound event interface and the orchestration query API meet a monthly availability target of 99.9 percent (approximately 43 minutes of downtime per month), measured from the load-balancer perspective and excluding scheduled maintenance announced at least 24 hours in advance. SC-005's recovery-from-outage criterion stands alongside as the acute-event constraint.

## Assumptions

- The upstream diagnostic system that emits findings is out of scope for this feature; for the purposes of this feature its output is a documented inbound event schema and findings are produced by a controllable simulator.
- The downstream collection control plane is out of scope; for the purposes of this feature it is a documented API surface and an in-process simulator that can be configured to inject failures during integration tests.
- Post-collection vehicle telemetry is out of scope; for the purposes of the feedback loop it is produced by a controllable telemetry generator parameterized by the deployed policy.
- Tenant isolation is not yet load-bearing in this feature; the system runs as a single tenant. The interfaces are designed so that adding tenant scoping in a later feature is a configuration and routing change, not a redesign.
- The hypothesis class for this feature is brake-wear early-stage anomaly. Other classes are recognized as out-of-scope and are rejected with a structured error rather than processed.
- Operator authentication uses an OAuth2 client-credentials grant per tenant. Every inbound event and every query carries a JWT bearer token, and the JWT MUST contain a non-empty `tenant_id` claim that the inbound interface uses to populate the composite finding key. Identity-provider details (issuer URL, JWKS endpoint, key rotation cadence) are pinned in the plan; they are not user-facing in this feature.
- Personal-data handling defaults are conservative: any signal flagged as personally identifiable in the canonical vocabulary requires an explicit consent flag in the policy, and the system rejects such policies otherwise. The default consent state is "no consent."
- A "policy" is small enough to be delivered to vehicles without firmware updates; the size profile is in the kilobyte range and is recorded as part of the documented policy schema.
- Collection windows are expressed and stored in logical time. Production windows are bounded above at 168 hours (7 days); a policy whose requested window exceeds that bound MUST be rejected with a structured error. Tests run with a configurable time-acceleration factor that maps the same logical window to seconds of wall-clock; the factor is environment-scoped and is the only knob that affects scheduler clock advancement, so the same code path produces the same outcome record at production speed and at test speed.
- A finding is uniquely identified by a composite key `(tenant_id, finding_id)`. The `finding_id` is supplied by the upstream source; the `tenant_id` is supplied by the inbound interface based on the authenticated principal. The system enforces idempotency on the composite key and does not depend on payload content equality. In feature 001, `tenant_id` defaults to a constant; in feature 002 the same key shape continues to apply with multiple tenant values.
- Every error response from inbound and query interfaces follows a single structured shape: a stable error code, an HTTP-equivalent status, a human-readable reason, and an optional details object. Authentication and authorization failures MUST NOT echo the inbound payload or any token claim other than the rejection code; this is to prevent token leakage through error logs.
- PR-tier load tests use a deterministic policy-generator stub keyed by input fingerprint, returning canned schema-valid policy payloads that exercise the full downstream path. The stub is contract-tested against the real policy generator so it cannot drift from real behavior. Stub design and lifecycle are locked by ADR-0004.
- Rate limiting per tenant is deferred to feature 002. Feature 001 does not enforce per-tenant ingress rate limits beyond the global ingest capacity implied by SC-002.
- Generated policy payloads are code-signed at registry-write time using a project-owned signing key in feature 001; the signing-key rotation procedure is documented in the runbook. Integration with Sonatus Updater for signed-OTA delivery is deferred to a downstream feature.
- The PII-adjacent signal list is maintained as a versioned artifact at `config/vss/v6.0/pii_signals.yaml`, change-controlled by ADR per Constitution Principle X.
- A threat-model document for the inbound interface is deferred to `docs/security/threat-model.md`, drafted during `/speckit-plan`. Three threats are named here for spec-level traceability, each paired with the requirement that handles it: (1) spoofed tenant claim, handled by FR-002 (validated JWT signature plus mandatory non-empty `tenant_id` claim); (2) replayed event, handled by FR-002a (`exp` rejection of expired tokens) and FR-012 (idempotency on the composite key); (3) malformed payload that conforms structurally to the schema (semantic abuse), handled by FR-005 and FR-006 (canonical-vocabulary validation), FR-003a (unsupported `schema_version` rejection), and FR-017a (audit-record minimum field set ensuring traceability of the rejection).
