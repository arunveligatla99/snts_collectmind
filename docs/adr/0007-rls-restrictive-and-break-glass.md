# ADR-0007: Row-Level Security hardening posture + break-glass service-principal bypass

- Status: Proposed
- Date: 2026-05-11
- Deciders: Arun Veligatla (project author)
- Constitutional principle: X (Vehicle Telemetry Data Handling); IX (Security as a First-Class Requirement); XVII (Audit Is a Feature, Not a Log)

## Context

Feature 001 (the policy-loop vertical slice) shipped multi-tenant constructs from day one — the composite finding key `(tenant_id, finding_id)`, the JWT `tenant_id` claim, the `Database.acquire(tenant_id)` Row-Level Security context manager — but enforced the per-table RLS policies in `PERMISSIVE` mode, which is the right posture for a single-tenant vertical slice but the wrong posture for a multi-tenant platform. Constitutional Principle X requires per-tenant isolation enforced at the API gateway, the database row level, AND the deployment client; feature 001's readiness review explicitly carries the obligation forward to feature 002 ([`docs/runbook/feature-001-readiness-review.md`](../runbook/feature-001-readiness-review.md) §Principle X).

The `audit_events` table in particular requires a more nuanced posture than other tenant-scoped tables. Most tenant data is owned by exactly one tenant and is invisible to every other tenant under all circumstances. Audit data is the same in the steady state, but mature multi-tenant platforms also need a documented, audited path for cross-tenant audit reads under specific, narrow circumstances: cross-tenant incident response (an operator investigating a security incident that crosses tenant boundaries), legal-hold retrieval (audit evidence subpoenaed by a regulator or court), regulator inquiry, and operator support escalation (a tenant has reported a problem the operator needs to diagnose by reading the tenant's audit trail). Pretending these use cases don't exist either forces them into a different system (defeating Principle XVII's queryability requirement) or leaves the audit chain too permissive to satisfy Principle X.

This ADR records the two coupled decisions: (1) the RLS hardening posture across every tenant-scoped table; (2) the break-glass service-principal bypass primitive that lets `audit_events` participate in cross-tenant operator workflows without weakening the default isolation posture. The clarify session of 2026-05-11 selected the hybrid posture (Spec FR-005); this ADR records the decision in the form expected by Principle XVIII (Governance and Escalation).

## Decision

### Part 1 — RLS hardening: `PERMISSIVE` → `RESTRICTIVE` on every tenant-scoped table

Apply RESTRICTIVE Row-Level Security policies to every tenant-scoped table that exists at the start of feature 002: `tenants` (the directory; service-principal-only writes), `diagnostic_findings`, `collection_policies`, `deployment_targets`, `policy_outcomes`, `audit_events`, `telemetry_observations` (TimescaleDB hypertable), `erasure_requests`, plus the three new tables introduced by this feature (`tenant_config`, `tenant_vehicles`, `tenant_vehicles_history`).

Each table's RESTRICTIVE policy enforces both:

- **Missing-context defense** — `current_setting('app.tenant_id', true) IS NOT NULL`. A database session that has not set `app.tenant_id` returns zero rows from any `SELECT` and is denied every `INSERT`/`UPDATE`/`DELETE` against the table. This is the failure-closed property: the absence of a context cannot leak rows.
- **Wrong-context defense** — `tenant_id = current_setting('app.tenant_id', true)::TEXT`. A database session whose `app.tenant_id` is set to tenant A returns zero rows when a `SELECT` targets tenant B's primary key, and is denied every `INSERT`/`UPDATE`/`DELETE` whose target row's `tenant_id` does not match the session's context.

The `WITH CHECK` clause on `INSERT`/`UPDATE` policies ensures the row being written carries a `tenant_id` matching the session context, refusing cross-tenant writes from inside a tenant context.

### Part 2 — Migration safety: roll-forward, roll-back, rolling deploy

The migration ships as `011_rls_restrictive.up.sql` + `011_rls_restrictive.down.sql` in the existing `src/collectmind/registry/migrations/sql/` directory. The forward migration:

1. Drops the existing `PERMISSIVE` policy on each table.
2. Creates the new `RESTRICTIVE` policy with both defenses.
3. Re-grants `SELECT`/`INSERT`/`UPDATE`/`DELETE` to the tenant-scoped role (the policy gates visibility, not the grants).
4. Issues `NOTIFY app_event, 'rls_restrictive_applied'` so the orchestration-api can log the cutover.

The backward migration reverses each step. SC-010 budgets ≤30 seconds for each direction; the migration suite test (`tests/integration/test_rls_migration_rollback.py`) asserts both budgets against a fresh testcontainer Postgres.

**Rolling-deploy safety**. The RESTRICTIVE policies are a strict superset of the PERMISSIVE policies (every row visible under RESTRICTIVE is also visible under PERMISSIVE). During a rolling deploy where some orchestration-api containers run on the pre-migration codebase and some on the post-migration codebase, the mixed fleet degrades gracefully: some requests may see fewer rows than they would post-rollout, but never more. Forward migration is therefore safe under rolling deploy without any application-layer feature flag. The backward migration is also safe (RESTRICTIVE → PERMISSIVE widens visibility, never narrows). Both directions are tested explicitly.

### Part 3 — Connection-pool transaction-boundary contract

The `Database.acquire(tenant_id)` context manager (shipped in feature 001) MUST issue `SET LOCAL app.tenant_id = $tenant_id` at the start of every transaction, not at connection-checkout time. `SET LOCAL` is scoped to the current transaction; on commit/rollback the setting reverts to NULL. The next transaction's first `SELECT` reads NULL for `app.tenant_id` and (per the missing-context defense) returns zero rows until the next `SET LOCAL` lands.

The contract is enforced by `tests/integration/test_rls_restrictive.py::test_stale_gucs_fail_closed`, which:

1. Opens a connection from the pool.
2. Starts transaction 1, sets `app.tenant_id = 'tenant-a'`, reads tenant-a's row (visible), commits.
3. Starts transaction 2 WITHOUT setting `app.tenant_id`, reads tenant-a's row (must be invisible — failure-closed).

This guards against the most insidious cross-tenant leak: a connection-pool reuse where the second-use transaction inherits a stale GUC from the first-use. Postgres's `SET LOCAL` semantics make this guarantee structural, not policy-dependent.

### Part 4 — Break-glass bypass primitive

A narrowly scoped service-principal bypass primitive lets a break-glass operator query read `audit_events` rows for a tenant other than the requesting principal's home tenant. The primitive has the following shape, recorded in [`specs/002-multi-tenant-isolation/contracts/openapi/audit-admin.v1.yaml`](../../specs/002-multi-tenant-isolation/contracts/openapi/audit-admin.v1.yaml):

- **Surface**: a distinct API endpoint `POST /api/v1/audit/break-glass/query` mounted on a distinct FastAPI router (`src/collectmind/audit_admin/api.py`). The router shares no handler function with the regular audit-query endpoint at `GET /api/v1/audit/{cid}`. The two handlers have different request shapes, different response shapes, and different DB-access primitives.
- **Authentication**: a separate JWT issuer ("operator-issuer") signs operator-principal JWTs with the audience claim `collectmind-operator`. The tenant issuer signs tenant JWTs with the audience `collectmind-tenant`. The two are verified by the same PyJWT + JWKS pipeline parameterized over issuer URL + audience. Local-dev uses a static-signer container under Compose profile `operator-issuer`; cloud uses an internal-only ALB.
- **DB access**: the break-glass handler connects under a service-principal Postgres role (`collectmind_service_principal`) that bypasses RLS. The SELECT is parameterized on the operator-supplied `tenant_scope`; the bypass cannot widen its scope mid-flight (the SQL is a single prepared statement with `WHERE tenant_id = $1 AND correlation_id = $2`).
- **Atomic audit**: every invocation writes a `kind=break_glass` row to `audit_events` in the same transaction as the bypassed SELECT. The audit row's minimum field set (FR-005b): `operator_principal_subject`, `tenant_scope`, `reason_code` (drawn from a documented enumeration), `correlation_id`. If the audit-write fails, the transaction aborts and the response is 500 — the absence of the audit row is itself the failure signal.

### Part 5 — Why a distinct router, not a header or a query parameter

The clarify session selected the hybrid posture; the plan kickoff asked the implementation to choose how the bypass call signals "this is a privileged op" so the same code path doesn't accidentally get used for a routine query. We considered three options:

- (i) Distinct API endpoint with a distinct handler.
- (ii) Header (`X-Break-Glass-Reason: <code>`) on the regular endpoint that flips the bypass path.
- (iii) Query parameter (`?break_glass=true&reason=<code>`).

We pick option (i). The argument is build-time-impossibility vs runtime-guardedness:

- Option (ii) and (iii) put the bypass and the regular path on the same handler function with a runtime branch. A typo, a misordered conditional, or a future refactor can route a regular query through the bypass path. The failure mode requires constant vigilance at code-review time and can never be eliminated entirely.
- Option (i) makes the two paths different functions on different routers with different dependencies, different request schemas, and different response schemas. A PR that exposes the bypass on the regular API would fail the regular API's contract test on the response-shape mismatch; FastAPI cannot route the request to the break-glass handler unless the operator-principal dependency resolves; the dependency cannot resolve under a tenant JWT. The failure mode collapses to "did the PR add the wrong router import?" — a question answered at compile time.

The cost of option (i) is one extra OpenAPI document and one extra router registration. Both are trivial. The build-time guarantee is worth far more than the cost.

## Consequences

### Positive

- Every cross-tenant access path on every tenant-scoped table fails closed at the DB layer, independent of the application handler's correctness. Principle X's "enforced at the DB row level" is structural.
- The break-glass primitive participates in Principle XVII's audit queryability: every invocation produces a queryable, immutable audit row. The audit trail itself is the security artifact, not a structured log line that might be lost.
- The dual-issuer authentication scheme reuses every existing auth primitive (PyJWT, JWKS, FastAPI `Depends`). No new auth machinery; no new dependency surface; small audit surface.
- The distinct-router approach makes accidental bypass invocation a build-time impossibility. The failure mode collapses from "must vet every PR for runtime branch conditions" to "must vet every PR for correct router registration" — a much easier guarantee.
- Rolling-deploy safety is structural (RESTRICTIVE is a strict subset of PERMISSIVE's visibility); no feature flag needed.

### Negative

- Two JWT issuers means two JWKS caches, two signing-key rotation schedules, and two trust boundaries. The local-dev story is intact (a static signer container in Compose), but cloud operations now manages two issuer endpoints.
- A future operator-facing UI for the break-glass surface (out of scope for this feature) must be built against the dedicated endpoint, not retrofitted onto the regular audit-query UI. This is by design, but it's a real cost in future development.
- The `tenant_vehicles_history` RLS policy that allows visibility to either the prior owner or the new owner means a tenant can detect that a vehicle was transferred away from them (the row appears in their query results with `new_tenant_id != self`). This is intentional and is a feature (the tenant should know they no longer own the vehicle), but it is an information leak if interpreted strictly (the requesting tenant learns that some other tenant owns the vehicle now). The narrow leak is acceptable per Principle X's intent; if a future feature wants stricter erasure, an ADR amendment is the vehicle.

### Neutral

- The `SET LOCAL` contract is a stricter guarantee than `SET` at session level; existing application code under the `Database.acquire(tenant_id)` context manager already conforms because that context manager is the only way to get a tenant-scoped connection in feature 001.

## Alternatives considered

### RESTRICTIVE everywhere with no break-glass primitive (Spec FR-005 option A)

Rejected. Strict RESTRICTIVE on `audit_events` with no bypass means cross-tenant incident response, legal-hold retrieval, and operator support escalation each require either a new feature (an out-of-band audit-export tool, a parallel data store, or a hand-built ETL) or a deliberate Principle X deviation per incident. The first option duplicates infrastructure; the second normalizes Principle X violations under operational pressure. Both are worse than recording the bypass primitive once, audibly, and bounded.

### Service-principal bypass with no RESTRICTIVE policy on `audit_events` (Spec FR-005 option B)

Rejected. Leaves the database trusting the handler. Any future bug in the audit-query handler that forgets to apply tenant scoping leaks cross-tenant audit content. The defense-in-depth property the constitution requires (Principle X: "enforced at the API gateway, the database row level, AND the deployment client") fails at the DB layer for `audit_events` only — exactly the table where audit-trail leakage hurts most.

### IAM-based authentication for the bypass surface (research §3 option ii)

Rejected per research §3: strong in cloud but breaks the local-dev story; asymmetric with the rest of the application (all other authenticated endpoints use JWT); operator confusion about which boundary applies where.

### mTLS for the bypass surface (research §3 option iii)

Rejected per research §3: operational cost of cert issuance + rotation tooling; no support for browser-based operators in any future feature; no clear win over JWT for this use case.

### Header or query-parameter signaling (research §4 options ii, iii)

Rejected per the build-time-impossibility argument in §Decision Part 5.

## References

- [`specs/002-multi-tenant-isolation/spec.md`](../../specs/002-multi-tenant-isolation/spec.md) §Clarifications Q1, FR-005, FR-005a, FR-005b, FR-005c, SC-013
- [`specs/002-multi-tenant-isolation/research.md`](../../specs/002-multi-tenant-isolation/research.md) §3, §4
- [`specs/002-multi-tenant-isolation/data-model.md`](../../specs/002-multi-tenant-isolation/data-model.md) §RLS hardening of existing tables; §Connection-pool transaction-boundary contract
- [`specs/002-multi-tenant-isolation/contracts/openapi/audit-admin.v1.yaml`](../../specs/002-multi-tenant-isolation/contracts/openapi/audit-admin.v1.yaml)
- Constitutional principles X, IX, XVII at [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
- Feature-001 readiness review (Principle X carry-forward) at [`docs/runbook/feature-001-readiness-review.md`](../runbook/feature-001-readiness-review.md)
