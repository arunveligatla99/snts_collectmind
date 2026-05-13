# Feature Specification: Multi-Tenant Isolation

**Feature Branch**: `002-multi-tenant-isolation`
**Created**: 2026-05-11
**Status**: Draft
**Input**: User description: "Harden multi-tenant data isolation across the policy loop. Tighten Postgres Row-Level Security from PERMISSIVE to RESTRICTIVE on every tenant-scoped table; per-tenant ingress rate limiting on the inbound and query API surfaces; tighten the Redis hot-store key shape to include tenant identity; tighten the deployment client's tenant scoping; negative-path contract and integration tests proving cross-tenant access is impossible."

## Background

Feature 001 (the policy-loop vertical slice) shipped the end-to-end CollectMind value proposition under a deliberately narrow assumption: a single tenant. Multi-tenant constructs were laid in from day one — the composite finding key `(tenant_id, finding_id)`, the JWT `tenant_id` claim, the `Database.acquire(tenant_id)` Row-Level Security context manager, per-tenant metric labels — but the underlying isolation primitives were left at their permissive defaults so the vertical slice could ship without scope creep. The constitution's Principle X ("per-tenant data isolation MUST be enforced at the API gateway, the database row level, and the deployment client") is the binding contract; feature 001's readiness review records the obligation as carried forward to this feature.

This feature is the load-bearing cash-out of Principle X. It does not add new product surface; it converts every isolation primitive from permissive-by-construction to restrictive-by-construction, and proves the conversion with negative-path tests that exercise every cross-tenant attack surface. It also adds the operational primitive that Principle X implies but feature 001 did not need: per-tenant ingress rate limiting, so a single noisy tenant cannot degrade the shared infrastructure that other tenants depend on.

This is a defense-in-depth feature. Each isolation control (DB-level RLS, API-level handler scoping, hot-store key shape, deployment-client validation, ingress rate limiting) defends against a different failure mode of the others. Removing any one layer must still leave the system isolated; that posture is the testable contract.

### In scope

- Tightening Postgres Row-Level Security from `PERMISSIVE` to `RESTRICTIVE` on every tenant-scoped table that exists at the start of this feature: `collection_policies`, `deployment_targets`, `audit_events`, `telemetry_observations`, `erasure_requests`, and any additional tenant-scoped table introduced by feature 001 that carries a `tenant_id` column.
- Per-tenant ingress rate limiting on `POST /api/v1/findings` and on every `GET /api/v1/...` query endpoint, keyed by the verified JWT `tenant_id` claim.
- Tightening the Redis hot-store key shape from `vehicle_id:signal_name` to `tenant_id:vehicle_id:signal_name`, including a documented migration story for existing keys.
- Tightening the deployment client's tenant scoping so a deployment request can never be issued against a vehicle that does not belong to the requesting tenant; mismatch is a Fatal error class and is audited.
- Negative-path contract and integration tests that prove a tenant-A principal cannot read, write, or deploy against tenant-B data through any endpoint.
- Observability surface for tenant-scoped controls: rate-limit decisions emitted as RED metrics with a `tenant_id` label and as PII-stripped structured-log events; rate-limit breach panel on the Grafana dashboard; runbook page for the rate-limit alert.
- Migration safety: every schema and policy change MUST be safe to roll forward and back, with zero data loss and zero hard cutover.

### Explicitly out of scope

- Per-tenant encryption-at-rest with per-tenant Key Management Service keys (separate feature; gated on a separate cryptographic-architecture ADR).
- Per-tenant model fine-tuning or per-tenant Small Language Model variants (separate feature; gated on a Principle XIII constitution amendment).
- Cross-region tenant residency controls and data-locality enforcement (separate feature; gated on a deployment-topology ADR).
- A self-service tenant provisioning or onboarding flow (out of scope; this feature assumes tenants are provisioned by an operator out-of-band).
- The operator-facing surface for the FR-005a break-glass service-principal bypass (UI, CLI, escalation workflow, approval workflow, alerting on `break_glass` audit-row creation). Only the bypass primitive and the `break_glass` audit-row writer are in scope; the surface that consumes them is a separate feature.
- The operator-facing surface for tenant management — the UI, CLI, approval workflow, and change-review workflow that consume the FR-013 service-principal write primitive to mutate `tenant_config`. Only the `tenant_config` table, its Row-Level Security policy, the service-principal write primitive, and the `tenant_config_change` audit-row writer are in scope; the surface that consumes them is a separate feature.
- Per-tenant billing, quota accounting, or usage reporting beyond the rate-limit decision metrics emitted by this feature (separate feature).
- Changes to the JWT issuer, signing algorithm, or claim shape (the `tenant_id` claim already exists from feature 001 and is reused unchanged).

## Clarifications

### Session 2026-05-11

- Q: Audit-query API isolation posture (FR-005) → A: **Hybrid (option C).** RESTRICTIVE Row-Level Security on `audit_events` as default for every tenant-scoped read; a narrowly scoped service-principal bypass reserved for break-glass operator queries (cross-tenant incident response, legal-hold retrieval) under elevated audit. Binding constraint: every invocation of the bypass MUST write an immutable audit row of kind `break_glass` to `audit_events` carrying the operator principal subject, the tenant scope queried, a reason code, and the correlation identifier; structured logging alone is insufficient. In scope for this feature: the bypass primitive + the `break_glass` audit-row writer. Out of scope: the operator-facing surface (UI, CLI, escalation workflow).
- Q: Default per-tenant rate limit + burst capacity (FR-012) → A: **2x SLO headroom (option C).** Inbound default: 2000 requests per second sustained, burst capacity 4000. Query endpoints default: 200 requests per second sustained, burst capacity 400. Binding semantic: the rate limit is NOT the SLO. Feature-001 SC-002 (1000 events/s/tenant sustained at ≥99.9% success) is what the system promises a tenant; the rate limit protects shared infrastructure when one tenant misbehaves. Setting rate limit = SLO floor would make SLO compliance structurally unattainable (a tenant operating exactly at 1000 r/s sustained would hit the limiter and lose the ≥99.9% half). 2x SLO sustained with 4x SLO burst gives every tenant their full SLO budget plus 100% headroom; the limiter fires only when a tenant is sustaining double their entitlement, which is the noisy-neighbor case (US2). This distinction MUST be captured in FR-012's rationale so future operators do not lower the limit to "match the SLO."
- Q: Per-tenant rate-limit override storage (FR-013) → A: **Postgres `tenant_config` table (option A).** Persisted alongside the audit chain in the same database, runtime-reloadable via short-TTL cache + Postgres `LISTEN/NOTIFY`, no new external service surface. Binding constraints: (i) `tenant_config` MUST enforce Row-Level Security allowing tenant-scoped `SELECT` for the row owning a tenant identifier (so tenants can introspect their own configured limits via a query endpoint) but denying `INSERT`, `UPDATE`, and `DELETE` from any non-service principal; (ii) writes are service-principal-only and MUST produce a `kind=tenant_config_change` audit row in the same database transaction as the configuration write (same atomic-audit pattern as the FR-005a break-glass bypass). In scope for this feature: the table, the RLS policies, the service-principal write primitive, and the `tenant_config_change` audit-row writer. Out of scope: the operator-facing surface for tenant management (UI, CLI, approval workflow).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tenant data is isolated end-to-end and proven by negative-path tests (Priority: P1)

A platform operator onboards a second tenant onto an environment that already serves a first tenant. From that moment forward, no request authenticated as tenant A can read, write, or deploy against any data owned by tenant B, through any endpoint, under any failure mode of the application layer. The isolation is enforced both at the database row level (so an application-layer bug or omission still cannot leak data) and at the API handler layer (so a database-layer bug still cannot leak data). The operator can prove this property by running a negative-path test suite that exercises every endpoint with a deliberately wrong-tenant token and observes that every cross-tenant attempt returns a structured "not found" response, never reveals the existence of the other tenant's resource, and never returns its content.

**Why this priority**: This is the entire value proposition of the feature. Without it, multi-tenant isolation is an aspiration, not a contract. Every other story in this feature is a supporting concern that defends a specific layer of this property.

**Independent Test**: Can be fully tested by provisioning two tenants (A and B), creating one finding under each, and then exercising every read, write, deployment, and query endpoint with a tenant-A token against tenant-B's resource identifier. Every such request MUST return a "not found" response (not a "forbidden" response, which would be an existence oracle). The same suite, run against the database layer directly with a wrong-tenant Row-Level Security context, MUST return zero rows for every query.

**Acceptance Scenarios**:

1. **Given** tenants A and B each own one finding, one policy, one deployment, one audit chain, one telemetry observation, and one erasure request, **When** a tenant-A principal issues a `GET` against tenant-B's finding identifier on the inbound, query, audit, or erasure endpoints, **Then** the system returns a structured "not found" response within the read-latency budget, no row is returned, and no log line, metric label, or trace span reveals the existence or content of tenant-B's resource.
2. **Given** the same setup, **When** a tenant-A principal attempts to publish a finding whose payload claims tenant-B's identifier in any path parameter, body field, or header, **Then** the system rejects the request with a structured error before any side effect occurs, no policy is generated, no audit row is written for tenant B, and the rate-limit counter for tenant B is not advanced.
3. **Given** the same setup, **When** a database session is opened with the Row-Level Security context set to tenant A and a query targets tenant-B's primary key, **Then** zero rows are returned even when the row exists, the same result holds when the Row-Level Security context is unset, and the same result holds when the context is set to a tenant identifier that does not exist.
4. **Given** an immutable audit chain that already records a `generated`, `validated`, `deployed`, and `outcome` event for tenant A, **When** the same chain is queried via the audit-query API by a tenant-B principal using tenant A's correlation identifier, **Then** the response is a structured "not found" with no events leaked.
5. **Given** the negative-path contract test suite, **When** the suite runs in continuous integration against the real local stack, **Then** every endpoint declared in the OpenAPI surface is exercised at least once with a wrong-tenant token, every such call returns the documented "not found" status, and the suite fails the build if any cross-tenant call returns a 200, 403, 422, or 500 response.

---

### User Story 2 - A single noisy tenant cannot degrade other tenants (Priority: P2)

A platform operator runs a multi-tenant environment in which one tenant occasionally bursts well above its normal request rate, either accidentally (a misconfigured client) or by design (a backfill). When that tenant's burst exceeds its configured rate limit, the system rejects the over-budget requests with a structured "too many requests" response that names the retry interval, and the system continues to serve every other tenant within their normal latency budget. The on-call engineer can see, on the operational dashboard, which tenant is being throttled, by which endpoint, and at what rate, and is paged with a runbook link if the throttling persists past a configured duration.

**Why this priority**: A multi-tenant system without per-tenant ingress controls is single-tenant the moment one tenant misbehaves. This story is the operational primitive that makes per-tenant isolation durable under load. It is P2 rather than P1 because the isolation contract itself (US1) defends correctness; this story defends availability.

**Independent Test**: Can be fully tested by configuring a low rate limit for tenant A, sustaining a request rate well above that limit from tenant A while sustaining a request rate well below the limit from tenant B, and asserting that tenant A receives "too many requests" responses with a `Retry-After` header while tenant B continues to receive responses within the normal latency budget. The dashboard MUST show the tenant-A throttle rate, the alert MUST fire when the throttle is sustained, and the runbook page MUST be reachable from the alert.

**Acceptance Scenarios**:

1. **Given** tenants A and B each have a configured rate limit, **When** tenant A sustains a request rate above its configured limit, **Then** tenant A's over-budget requests receive a structured "too many requests" response with a `Retry-After` header, tenant A's metric counter for rejected requests advances, and tenant B's request latency stays within its normal budget for the duration of the burst.
2. **Given** the same setup, **When** the rate-limit decision is made, **Then** the decision is emitted as a structured log event that includes the tenant identifier, the endpoint, the decision (allow or reject), and the remaining budget, with no PII or raw payload included.
3. **Given** the operational dashboard is open, **When** any tenant is being throttled, **Then** a panel shows the throttle rate per tenant per endpoint within the dashboard-lag budget.
4. **Given** a tenant is throttled continuously beyond a configured duration, **When** the duration elapses, **Then** an alert fires, names the throttled tenant and endpoint, and links to a runbook page that describes the cause and the recovery procedure.
5. **Given** a tenant has a per-tenant override that raises or lowers its default rate limit, **When** the override is in effect, **Then** the rate-limit decisions for that tenant respect the override and the audit trail records who applied the override and when.

---

### User Story 3 - The hot store cannot leak telemetry across tenants on the same vehicle identifier (Priority: P2)

Two different tenants legitimately operate vehicles whose vehicle identifier strings happen to collide (the vehicle identifier is not globally unique across tenants — only within a tenant). The system MUST treat their hot-store telemetry as fully separate: a read by tenant A for vehicle `VIN-1` MUST never return any value written by tenant B for vehicle `VIN-1`, and the same property MUST hold under cache eviction, cache restart, and cache failover.

**Why this priority**: The hot store is a cache, but a cache that leaks across tenants is indistinguishable from a database that leaks across tenants. P2 because the contract (US1) covers the durable stores; this story covers the volatile store, which is shorter-lived but still load-bearing for operational correctness.

**Independent Test**: Can be fully tested by writing a value for tenant A under vehicle identifier `VIN-1` and signal name `Vehicle.Speed`, then issuing a read for tenant B under the same vehicle identifier and signal name, and asserting the read returns the cache-miss sentinel, not tenant A's value. The same test MUST pass after a cache restart and after a cache key migration from the legacy key shape to the tenant-scoped key shape.

**Acceptance Scenarios**:

1. **Given** the hot store is empty, **When** tenant A writes a telemetry value for vehicle `VIN-1`, **Then** tenant B's subsequent read for the same vehicle and signal returns a cache-miss sentinel, and tenant A's read returns the value tenant A wrote.
2. **Given** the hot store contains values written under the legacy key shape (no tenant prefix) from a prior version of the system, **When** the migration runs, **Then** every legacy key is removed or re-keyed under the tenant-scoped shape, and the system serves correct values for every tenant within the documented migration window with no data loss for the durable store.
3. **Given** the system is running under the new key shape, **When** an operator inspects the cache key namespace, **Then** every key carries an explicit tenant prefix and no key without a tenant prefix is observable.

---

### User Story 4 - The deployment client refuses to act outside the requesting tenant's scope (Priority: P3)

When the system generates and validates a policy on behalf of tenant A, the deployment-client node MUST refuse to issue a deployment request against any vehicle that does not belong to tenant A, even when the in-process policy state has been corrupted, manipulated, or tampered with at any earlier stage. The mismatch is a Fatal error class (not Recoverable), is written to the audit chain with the originating finding lineage, and is paged.

**Why this priority**: This is the last line of defense for cross-tenant isolation at the egress boundary. P3 because feature 001 already scopes deployments to the tenant by construction (the policy carries the tenant identifier from the originating finding); this story is the explicit re-validation at the egress that catches any upstream regression. It is the construction-side counterpart to US1's API-side and US3's cache-side defenses.

**Independent Test**: Can be fully tested by constructing a policy whose declared tenant identifier does not match its target vehicle identifier's owning tenant, attempting to deploy that policy, and asserting that the deployment-client node rejects the deployment with a Fatal error, no outbound call is made to the downstream control plane, an audit row is written that names the mismatch, and an alert fires.

**Acceptance Scenarios**:

1. **Given** a policy whose declared tenant identifier matches its target vehicle's owning tenant, **When** the deployment-client node receives the policy, **Then** the outbound deployment call proceeds within the latency budget and the deployment is audited as Recoverable success.
2. **Given** a policy whose declared tenant identifier does not match its target vehicle's owning tenant, **When** the deployment-client node receives the policy, **Then** no outbound deployment call is made, the deployment-client node raises a Fatal error class, an audit row is written that names the mismatch and the originating finding lineage, and a page-tier alert fires.
3. **Given** the deployment client has retried a transient downstream fault under its existing Recoverable retry posture, **When** the retried request still carries a tenant mismatch, **Then** the Fatal error class supersedes the Recoverable retry and the request is not retried again.

---

### Edge Cases

- A request arrives with a JWT whose `tenant_id` claim is empty, missing, or malformed: the system rejects the request with an authentication error, never inspects the payload, and never advances any tenant's rate-limit counter.
- A request arrives with a JWT whose `tenant_id` claim refers to a tenant that does not exist in the system: the system rejects the request with the same "not found" response shape it uses for cross-tenant access, so the response shape is not an existence oracle for valid-but-other-tenant identifiers.
- A long-running database transaction is opened and the connection is reused across requests with different tenant identifiers: the Row-Level Security context MUST be re-established on every transaction boundary; an attempt to reuse a stale context MUST fail closed (no rows returned) rather than silently leak.
- The hot-store key migration is interrupted mid-flight (process killed, cache restarted): the next run MUST pick up where the previous run left off without producing duplicate values, and the system MUST serve correct values for every tenant during the migration window.
- A rate-limit override is configured for a tenant that does not exist: the system rejects the override with a structured error and never advances any rate-limit counter for the non-existent tenant.
- The deployment client receives a policy whose tenant identifier matches its target but whose target vehicle identifier collides with a vehicle owned by a different tenant: the deployment client MUST refuse the deployment based on the vehicle's owning-tenant lookup, not on the policy's declared tenant identifier alone.
- A negative-path test suite is run against an environment where Row-Level Security is disabled (for example, a misconfigured staging environment): the suite MUST fail loudly, name the missing isolation primitive, and refuse to mark itself as passing.
- A tenant's rate limit is exceeded while a long-running request is in flight: the in-flight request completes within its existing latency budget; only subsequent requests are throttled.

## Requirements *(mandatory)*

### Functional Requirements

#### Database-level isolation (US1)

- **FR-001**: System MUST enforce Row-Level Security in `RESTRICTIVE` mode on every tenant-scoped table that carries a `tenant_id` column.
- **FR-002**: System MUST defend against the missing-context case: a database session that has not set the tenant context MUST return zero rows from any `SELECT`, MUST reject any `INSERT`, `UPDATE`, or `DELETE` against any tenant-scoped table, and MUST never expose row contents through error messages.
- **FR-003**: System MUST defend against the wrong-context case: a database session whose tenant context is set to tenant A MUST return zero rows when a `SELECT` targets tenant B's primary key, MUST reject any `INSERT` whose `tenant_id` column does not match the session context, and MUST reject any `UPDATE` or `DELETE` whose target row's `tenant_id` does not match.
- **FR-004**: System MUST migrate from the existing `PERMISSIVE` Row-Level Security policies to `RESTRICTIVE` policies in a manner that is safe to roll forward and back: the migration MUST be applicable on a running system without requiring a hard cutover, MUST be rollbackable to the prior `PERMISSIVE` policy without data loss, and MUST be tested against both directions in the migration suite.
- **FR-005**: System MUST enforce RESTRICTIVE Row-Level Security on `audit_events` for every tenant-scoped read by default; the audit-query API handler MUST run under the requesting tenant's Row-Level Security context, identical to every other tenant-scoped read endpoint, so the database is the authoritative isolation boundary for the audit-query path. Cross-tenant audit reads are reachable only via the narrowly scoped service-principal bypass defined in FR-005a, never through the regular audit-query API.
- **FR-005a**: System MUST provide a narrowly scoped service-principal bypass primitive that allows a break-glass operator query to read `audit_events` rows belonging to a tenant other than the requesting principal's home tenant, intended for cross-tenant incident response and legal-hold retrieval. The bypass MUST require an operator-principal identity (distinct from any tenant-scoped JWT), a tenant scope (the target tenant identifier whose rows are being read), and a reason code drawn from a documented enumeration. The bypass MUST refuse to read rows outside the named tenant scope; a single invocation MUST NOT widen its scope mid-flight.
- **FR-005b**: Every invocation of the FR-005a bypass MUST write an immutable audit row of kind `break_glass` to `audit_events` before any bypassed read returns to the caller. The row's minimum field set MUST include (i) the operator principal subject, (ii) the tenant scope queried, (iii) the reason code, and (iv) the correlation identifier; the row MUST be subject to the same immutability triggers and Principle XVII queryability as every other audit row kind. Structured logging alone is insufficient; the audit row is the queryable, immutable artifact that satisfies Principle XVII for break-glass usage.
- **FR-005c**: Scope boundary for FR-005a/FR-005b: the bypass primitive and the `break_glass` audit-row writer are in scope for this feature. The operator-facing surface that consumes the primitive (UI, CLI, escalation workflow, approval workflow, alerting on break-glass-row creation) is out of scope and is a separate feature.

#### API-level isolation (US1)

- **FR-006**: System MUST return a structured "not found" response (not "forbidden", not "unauthorized", not "unprocessable entity") for every cross-tenant access attempt on every read, write, deployment, and query endpoint, so that the response shape does not act as an existence oracle.
- **FR-007**: System MUST extract the tenant identifier exclusively from the verified JWT `tenant_id` claim on every authenticated request and MUST ignore any tenant identifier supplied in path parameters, query parameters, request bodies, or headers, except as a target identifier whose ownership MUST be re-validated against the JWT claim.
- **FR-008**: System MUST propagate the JWT-derived tenant identifier to every downstream layer (the database session's tenant context, the hot-store key prefix, the deployment client's scoping check, the metric labels, the structured log fields, the trace span attributes) within the same request scope and MUST never substitute a different value mid-request.
- **FR-009**: System MUST never include a different tenant's identifier or any of its resource identifiers in any log line, metric label value, trace span attribute, or response body produced by a cross-tenant access attempt.

#### Per-tenant ingress rate limiting (US2)

- **FR-010**: System MUST enforce a per-tenant rate limit on `POST /api/v1/findings` and on every `GET /api/v1/...` query endpoint, keyed by the verified JWT `tenant_id` claim.
- **FR-011**: System MUST respond to over-budget requests with a structured "too many requests" response that includes a `Retry-After` header indicating the time at which the next request from that tenant is expected to be allowed.
- **FR-012**: System MUST apply a documented default rate limit and burst capacity to every tenant in the absence of an explicit override. Default values: the inbound endpoint (`POST /api/v1/findings`) MUST default to 2000 requests per second sustained with a burst capacity of 4000; every `GET /api/v1/...` query endpoint MUST default to 200 requests per second sustained with a burst capacity of 400. These defaults MUST be documented in a runbook page alongside the rationale in FR-012a.
- **FR-012a**: The runbook page that documents FR-012's defaults MUST capture the binding rate-limit-versus-SLO distinction: the rate limit is NOT the service-level objective. Feature-001 SC-002 (1000 events/s/tenant sustained at ≥99.9% success) is what the system promises a tenant; the rate limit is what protects shared infrastructure when one tenant misbehaves. Setting the rate limit equal to the SLO floor would make SLO compliance structurally unattainable: a tenant operating exactly at 1000 r/s sustained would hit the limiter and fail the ≥99.9% half of SC-002. The 2x-SLO sustained / 4x-SLO burst defaults give every tenant the full SLO budget plus 100% headroom; the limiter fires only when a tenant is sustaining double their entitlement, which is the noisy-neighbor case (US2). The runbook MUST warn future operators against lowering the inbound default to "match the SLO."
- **FR-013**: System MUST support per-tenant overrides of the default rate limit and burst capacity, persisted in a Postgres table named `tenant_config` colocated with the existing audit chain. The table MUST carry `tenant_id` as its scoping column and MUST be reloadable at runtime by the orchestration-api process within a documented short-TTL cache window (Postgres `LISTEN/NOTIFY` or equivalent), without requiring a container restart or a redeploy.
- **FR-013a**: System MUST enforce Row-Level Security on `tenant_config` as RESTRICTIVE in line with FR-001. The Row-Level Security policy MUST allow tenant-scoped `SELECT` for a principal whose JWT-derived tenant identifier matches the row's `tenant_id` (so tenants can introspect their own configured limits via a documented query endpoint), MUST deny `SELECT` for any cross-tenant principal, and MUST deny `INSERT`, `UPDATE`, and `DELETE` from every principal except the documented service principal.
- **FR-013b**: Every write to `tenant_config` (an `INSERT`, `UPDATE`, or `DELETE`) by the service principal MUST produce a `kind=tenant_config_change` audit row in `audit_events` inside the same database transaction as the write; if the audit-row write fails the configuration write MUST be rolled back. The audit row's minimum field set MUST include (i) the service principal subject, (ii) the target tenant identifier, (iii) the prior configuration values (or null on `INSERT`), (iv) the new configuration values (or null on `DELETE`), and (v) the correlation identifier; the row MUST be subject to the same immutability triggers and Principle XVII queryability as every other audit-row kind. This atomic-audit pattern mirrors the FR-005a/FR-005b break-glass bypass.
- **FR-013c**: Scope boundary for FR-013/FR-013a/FR-013b: the `tenant_config` table, the Row-Level Security policy, the service-principal write primitive, and the `tenant_config_change` audit-row writer are in scope for this feature. The operator-facing surface that consumes the write primitive (UI, CLI, approval workflow, change-review workflow) is out of scope and is a separate feature.
- **FR-014**: System MUST emit every rate-limit decision (allow or reject) as a Prometheus metric with a `tenant_id` label and as a structured log event that includes the tenant identifier, the endpoint, the decision, and the remaining budget; the structured log event MUST be PII-stripped by the same processor that strips PII from every other structured log event.
- **FR-015**: System MUST surface a per-tenant per-endpoint throttle-rate panel on the operational Grafana dashboard within the dashboard-lag budget (SC-006).
- **FR-016**: System MUST fire a page-tier alert when any tenant is throttled continuously for longer than a configured duration; the alert MUST name the tenant and the endpoint and MUST link to a runbook page that describes the cause and the recovery procedure.
- **FR-017**: System MUST never charge a rate-limit counter against a tenant for a request that fails authentication; rate-limit decisions MUST be made only after the JWT is verified.

#### Hot-store key tenancy (US3)

- **FR-018**: System MUST key every hot-store telemetry entry under a tenant-scoped key shape that includes the tenant identifier as a prefix, so that two tenants writing to the same vehicle identifier and signal name cannot collide.
- **FR-019**: System MUST migrate any existing hot-store entries from the legacy key shape to the tenant-scoped key shape; because the hot store is a cache, drop-and-rehydrate is acceptable provided the migration window stays inside the recovery-from-outage budget (FR-022a / SC-005 from feature 001) and no durable store loses data.
- **FR-020**: System MUST refuse to read or write any hot-store entry under the legacy key shape after the migration has run; an attempt to do so MUST raise a Fatal error class and MUST be audited.

#### Deployment-client tenant scoping (US4)

- **FR-021**: System MUST validate, at the deployment-client node before any outbound call, that every target vehicle identifier in the policy belongs to the tenant identifier declared on the policy, by looking up the vehicle's owning tenant in the canonical tenant-vehicle ownership store.
- **FR-022**: System MUST raise a Fatal error class (not Recoverable) on a tenant-vehicle mismatch and MUST NOT retry the deployment.
- **FR-023**: System MUST write an audit row of kind `deployment_rejected` for every Fatal tenant-vehicle mismatch, carrying the originating finding lineage, the policy reference, the rejected target vehicle identifier, the policy's declared tenant identifier, and the vehicle's owning tenant identifier (the latter MUST NOT be a different tenant's identifier visible to the requesting tenant; the audit row is consumed by the platform operator, not by the requesting tenant).
- **FR-024**: System MUST fire a page-tier alert on every Fatal tenant-vehicle mismatch and MUST link to a runbook page that describes the cause and the response.

#### Negative-path test surface (US1)

- **FR-025**: System MUST ship a contract-tier test suite that exercises every endpoint declared in the OpenAPI surface with a wrong-tenant token and asserts that every such call returns the documented "not found" status; the suite MUST fail the build if any cross-tenant call returns a 200, 403, 422, or 500 response.
- **FR-026**: System MUST ship an integration-tier test suite that exercises end-to-end cross-tenant attack scenarios against the real local stack: a tenant-A principal attempting to read tenant-B's audit chain, a tenant-A principal attempting to publish a finding under tenant-B's identifier, a database session with a wrong-tenant context attempting to read another tenant's policy, and a hot-store key collision attempt across tenants.
- **FR-027**: System MUST ship a unit-tier test that asserts the negative-path suites refuse to mark themselves as passing when Row-Level Security is disabled or when the rate-limiting middleware is removed (the "loud failure" property of FR-027 is the meta-test that protects the contract).

#### Migration safety and operational primitives

- **FR-028**: System MUST document the rollback procedure for the Row-Level Security migration, the hot-store key migration, and the rate-limit middleware introduction in the runbook, with a page per migration that names the rollback command, the rollback validation, and the rollback impact.
- **FR-029**: System MUST preserve the feature-001 recovery-from-outage property (SC-005): the rate-limit middleware, the Row-Level Security migration, and the hot-store key migration MUST NOT increase the system's recovery-from-outage budget beyond the existing 5-minute drain window.

### Key Entities *(include if feature involves data)*

- **Tenant**: A logically isolated customer of the system. Identified by a stable `tenant_id` string carried in every JWT, propagated to every layer, and used as the partition key for every isolation control. Tenants have configured rate limits (a default plus optional overrides), are owned by a platform operator, and are the unit of audit for cross-tenant access attempts.
- **Tenant-Vehicle Ownership**: The canonical mapping from a vehicle identifier to its owning tenant. Used by the deployment-client node to validate that a policy's target vehicles belong to the policy's declared tenant. The mapping is queried on every deployment and is the source of truth for vehicle ownership; vehicle identifiers are unique within a tenant but not across tenants.
- **Rate-Limit Configuration**: A per-tenant record carrying the request-rate ceiling and burst capacity for the inbound and query endpoints. Composed of a default (applied to every tenant in the absence of an override) and a set of per-tenant overrides (applied when present). Every change to the configuration is audited.
- **Rate-Limit Decision**: A per-request observation recording that a request from a given tenant was allowed or rejected. Emitted as a Prometheus metric with a `tenant_id` label, a structured log event (PII-stripped), and a counter that drives the dashboard panel and the page-tier alert.
- **Cross-Tenant Access Attempt**: A request whose JWT-derived tenant identifier does not match the tenant identifier of the targeted resource. Emitted as a structured log event (without leaking the targeted resource's tenant identifier or content), counted as a metric, and surfaced on the dashboard as a security-tier signal.
- **Break-Glass Audit Event**: An immutable `audit_events` row of kind `break_glass` written on every invocation of the FR-005a service-principal bypass. Carries the operator principal subject, the target tenant scope, a reason code drawn from a documented enumeration, and the correlation identifier. Subject to the same immutability triggers and Principle XVII queryability as every other audit-row kind; never redacted by the right-to-erasure dispatcher (the operator principal subject is not tenant PII).
- **Tenant Configuration Row**: A `tenant_config` table row keyed by `tenant_id`. Carries the per-tenant rate-limit overrides for the inbound and query endpoints (sustained rate, burst capacity), defaulting to FR-012's values when no override row exists. Subject to RESTRICTIVE Row-Level Security per FR-013a; writeable only by the documented service principal.
- **Tenant Configuration Change Audit Event**: An immutable `audit_events` row of kind `tenant_config_change` written in the same transaction as every `tenant_config` write per FR-013b. Carries the service principal subject, the target tenant identifier, the prior and new configuration values, and the correlation identifier. Subject to the same immutability triggers and Principle XVII queryability as every other audit-row kind.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every cross-tenant access attempt across every endpoint declared in the OpenAPI surface returns a "not found" response and never returns a "forbidden", "unauthorized", "unprocessable entity", or "internal server error" response, measured by the negative-path contract test suite running on every pull request.
- **SC-002**: Every cross-tenant database query returns zero rows when the Row-Level Security context is set to a tenant that does not own the targeted row, measured by the negative-path integration test suite running on every pull request.
- **SC-003**: A tenant sustaining a request rate at five times its configured rate limit MUST have at least 80 percent of its over-budget requests rejected with a structured "too many requests" response, measured by the rate-limit load profile in the smoke load tier.
- **SC-004**: A second tenant sustaining a request rate well within its configured rate limit, while the first tenant is bursting at five times its limit, MUST experience no measurable degradation of its end-to-end policy-loop latency (p95 stays within the SC-001 budget from feature 001), measured by the noisy-neighbor load profile in the smoke load tier.
- **SC-005**: The end-to-end policy-loop latency budget from feature 001 (SC-001: p50 under 4 seconds, p95 under 12 seconds, p99 under 30 seconds) MUST be preserved within 10 percent of its feature-001 baseline after the rate-limit middleware, the Row-Level Security RESTRICTIVE policies, and the tenant-vehicle ownership lookup are introduced; measured by the existing latency load profile.
- **SC-006**: The hot-store read path latency budget from feature 001 (Constitution Principle XI: p95 under 10 ms) MUST be preserved within 10 percent of its feature-001 baseline after the tenant-scoped key shape is introduced; measured by a hot-store-only load profile.
- **SC-007**: 100 percent of structured log events emitted by the rate-limit middleware MUST pass the PII-strip CI gate (T142, inherited from feature-001 Phase 7); measured by the existing PII-strip CI gate.
- **SC-008**: 100 percent of rate-limit decisions emitted as Prometheus metrics MUST carry a `tenant_id` label that matches the JWT-derived tenant identifier; measured by a unit-tier assertion against every rate-limit decision sample.
- **SC-009**: The hot-store key migration MUST complete in under 60 seconds against a hot store with up to 10,000 keys (the expected feature-001 steady-state size), measured by a one-shot migration script invoked from the migration suite.
- **SC-010**: The Row-Level Security RESTRICTIVE migration MUST apply on a running system in under 30 seconds and MUST be rollbackable in the same time, measured by the migration suite running both directions.
- **SC-011**: The negative-path integration test suite MUST cover every endpoint declared in the OpenAPI surface and every tenant-scoped table declared in the database schema, measured by a coverage assertion that fails the build when any new endpoint or any new tenant-scoped table is added without a corresponding negative-path test.
- **SC-012**: A page-tier alert MUST fire within 60 seconds of a Fatal tenant-vehicle deployment-client mismatch, measured by the alert-routing integration test (inherited from feature-001 T107).
- **SC-013**: 100 percent of FR-005a service-principal bypass invocations MUST produce a corresponding `kind=break_glass` row in `audit_events` carrying the FR-005b minimum field set (operator principal subject, target tenant scope, reason code, correlation identifier) before any bypassed read returns to the caller, measured by an integration-tier assertion that drives the bypass once per documented reason code and queries `audit_events` for the matching row.
- **SC-014**: 100 percent of `tenant_config` writes by the service principal MUST produce a corresponding `kind=tenant_config_change` row in `audit_events` carrying the FR-013b minimum field set (service principal subject, target tenant identifier, prior values, new values, correlation identifier) inside the same database transaction; a deliberately failing audit-row write MUST cause the configuration write to roll back. Measured by an integration-tier assertion that drives an override `INSERT`, `UPDATE`, and `DELETE` against a real Postgres stack and queries `audit_events` for the matching rows, plus a negative-path assertion that injects an audit-write failure and asserts the configuration row is absent.

## Assumptions

- The composite finding key `(tenant_id, finding_id)` and the JWT `tenant_id` claim already exist from feature 001 (per Clarifications Q1 of feature 001) and are reused unchanged. This feature does not change the JWT issuer, the JWT signing algorithm, or the JWT claim shape.
- The `Database.acquire(tenant_id)` Row-Level Security context manager already exists from feature 001 (per the readiness review, Principle X evidence) and is reused unchanged. This feature changes the policies enforced inside that context, not the context primitive itself.
- Per-tenant metric labels and the `tenant_id` field on every structured log event already exist from feature 001 and are reused unchanged. This feature adds new metrics and log events that follow the existing conventions.
- The hot store (Redis) is a cache; durable telemetry data lives in TimescaleDB and is not at risk during the hot-store key migration. Drop-and-rehydrate is acceptable for the hot-store migration provided the durable store remains intact.
- The hot-store key migration runs as a one-shot script invoked from the deployment pipeline at the cutover boundary, rather than as a startup hook on every container or as a background flush-and-rehydrate; this default may be revisited in `/speckit.clarify`.
- Tenant provisioning is an out-of-band operator workflow that already exists; this feature does not introduce a self-service tenant provisioning flow. The tenant identifier set is finite and known to the operator.
- The canonical tenant-vehicle ownership store exists and is queryable at deployment-client request time within an acceptable latency budget; this feature reuses the existing store rather than introducing a new one. (If the canonical store does not yet exist, that is a finding for `/speckit.plan` to surface as a blocking dependency.)
- The PII-strip CI gate (T142, Phase 7 follow-up from feature 001) lands either before or alongside this feature; SC-007 depends on it being in place.
- The constitutional non-negotiables IV (tests load-bearing), VII (CI gates merges), IX (security first-class), X (vehicle telemetry data handling), XI (SLOs measured), XIII (SLM-first), and XIV (deterministic budgeted CI) inherit from feature 001; this feature MUST satisfy each one, and the readiness review for this feature MUST walk each non-negotiable with a named artifact, mirroring the format of `docs/runbook/feature-001-readiness-review.md`.
- The three `[NEEDS CLARIFICATION]` markers from the initial draft (FR-005, FR-012, FR-013) were resolved in the `/speckit.clarify` session of 2026-05-11; the answers are recorded under `## Clarifications` and inlined into the corresponding Functional Requirements. The fourth open question from the initial draft (the hot-store key migration mechanism) is captured in this Assumptions section above as a default (one-shot script invoked from the deployment pipeline at the cutover boundary) and was not surfaced as a `[NEEDS CLARIFICATION]` marker, per the spec-template's three-marker limit. The default may be revisited during `/speckit.plan`.

## Dependencies

- Feature 001 (`policy-loop-vertical-slice`) at commit `990b437` + `a49939e` is the inherited baseline. Every primitive this feature tightens (Row-Level Security context, JWT `tenant_id` claim, composite finding key, per-tenant metric labels, hot-store key shape, deployment-client topology, audit chain) ships from feature 001.
- The constitution v1.0.1 at `.specify/memory/constitution.md`, particularly Principles X (Vehicle Telemetry Data Handling), IX (Security as a First-Class Requirement), IV (Tests Are Load-Bearing), and XI (Performance SLOs Are Measured, Not Aspired).
- The Phase 7 follow-up T142 (PII-strip CI gate, closes feature-001 SC-007) is an upstream dependency of this feature's SC-007.
