# ADR-0009: Tenant-Vehicle Ownership store — mutable current row + append-only history

- Status: **Accepted** (promoted at feature-002 Phase 9.b closure; Part 4 cache + Part 6 deployer hot-path validation re-attested at feature-002 closure per [`docs/runbook/feature-002-readiness-review.md`](../runbook/feature-002-readiness-review.md))
- Date: 2026-05-11 (proposed); 2026-05-12 (accepted at feature-002 closure)
- Deciders: Arun Veligatla (project author)
- Constitutional principle: X (Vehicle Telemetry Data Handling); XVII (Audit Is a Feature, Not a Log); II (No Mocked Subsystems Where a Real One Is Feasible)

## Context

Feature 002's deployment-client tenant scoping (Spec US4, FR-021) requires the deployer node to validate, before any outbound deployment call, that every target vehicle identifier in the policy belongs to the tenant identifier declared on the policy. The validation requires an authoritative source of truth for vehicle-to-tenant ownership.

The draft spec (in its Assumptions section) said "the canonical tenant-vehicle ownership store exists and is queryable at deployment-client request time within an acceptable latency budget; this feature reuses the existing store rather than introducing a new one. (If the canonical store does not yet exist, that is a finding for `/speckit.plan` to surface as a blocking dependency.)" The plan-kickoff surfaced this as wrong: feature 001 does NOT ship a canonical tenant-vehicle ownership store, so feature 002 must introduce one. This ADR records the data-model decision and its rationale.

Three design choices feed in:

1. **Store shape**: a relational table colocated with the existing tenant-scoped tables (Postgres) versus a separate data store. The constitution's Principle II ("no mocked subsystems where a real one is feasible") plus the existing Postgres-as-source-of-truth pattern point at the colocated relational table.
2. **Mutability**: a vehicle's owning tenant is a mutable attribute that changes over time (fleet sale, OEM-to-customer handoff, resale, lease return, decommission) versus an immutable assignment (a vehicle is forever tied to its initial tenant).
3. **Cache shape**: an in-process cache versus a Redis lookup cache versus uncached Postgres reads on every deployment.

The first choice is straightforward (relational, in Postgres). The third is also straightforward (Redis write-through cache with TTL, backed by Postgres). The second is the load-bearing decision and is what this ADR primarily records.

## Decision

### Part 1 — Mutable current row + append-only history table

Ownership is stored across two tables:

- `tenant_vehicles` — the **current** owner of each vehicle. Exactly one row per `vehicle_id`. The `tenant_id` column is mutable; service-principal writes via the operator workflow can update the current owner.
- `tenant_vehicles_history` — an **append-only** log of every ownership transition. Triggered by `BEFORE INSERT OR UPDATE OF tenant_id` on `tenant_vehicles`; one row per transition recording `vehicle_id`, `prev_tenant_id` (NULL on initial provisioning), `new_tenant_id`, `operator_subject`, `reason_code` (drawn from a documented enumeration: `initial_provisioning`, `resale`, `fleet_reassignment`, `oem_handoff`, `lease_return`, `totaled`, `other`), `transition_at`, `correlation_id`. Immutability enforced by row-level trigger that raises on any `UPDATE` or `DELETE` attempt.

Schema and RLS details at [`specs/002-multi-tenant-isolation/data-model.md`](../../specs/002-multi-tenant-isolation/data-model.md) §New table: `tenant_vehicles` + `tenant_vehicles_history`.

### Part 2 — Why mutable, not immutable

Operational reality is mutable. Vehicle-to-tenant assignments change for documented business reasons:

- **Fleet sales**: a fleet management company sells a fleet of vehicles to a new operator; every vehicle's owning tenant changes in a single transaction.
- **OEM-to-customer handoff**: the OEM provisions vehicles into an operator's fleet for the duration of the warranty period, then transfers ownership to the operator at the handoff.
- **Resale**: a used vehicle is sold from one fleet to another (B2B used-vehicle market).
- **Lease return**: a leased vehicle returns to the leasing company at end of lease; the owning tenant transitions from lessee to lessor.
- **Decommissioning**: a totaled or scrapped vehicle transitions to a sentinel `decommissioned` tenant; no further deployments are issued.

An immutable assignment forces a new `vehicle_id` per ownership change. The consequences cascade:

- **VIN-as-identifier semantics break**. The Vehicle Identification Number is durable for the life of the vehicle (17 characters, standardized by ISO 3779). Minting a synthetic `vehicle_id` per tenant transfer means the application no longer uses the VIN as its key; the joining layer becomes an indirection table mapping (synthetic_id, vehicle_id) which every consumer (registry, deployer, query-api, telemetry hypertable) must learn.
- **Telemetry-history continuity breaks**. The TimescaleDB `telemetry_observations` hypertable is partitioned by `vehicle_id`; an immutable model splits a vehicle's lifetime telemetry across N synthetic ids, breaking the join from the policy registry to the telemetry history without an explicit "this synthetic id is the same VIN as those other synthetic ids" reconciliation table.
- **Policy lineage breaks**. A policy generated for tenant A targeting VIN-X cannot be audited for the same vehicle after the VIN transfers to tenant B, because tenant B's view of the policy lineage references a different synthetic id.

The append-only history table provides everything immutability would have given:

- **Full chain-of-custody**. `SELECT * FROM tenant_vehicles_history WHERE vehicle_id = $1 ORDER BY transition_at` returns the complete ownership history.
- **Operator-readable cross-tenant lineage**. Operators with the FR-005a break-glass primitive can query across tenant boundaries (e.g., to investigate a chain-of-custody question raised by a regulator).
- **Per-tenant scoped reads**. The RLS policy on `tenant_vehicles_history` allows visibility only to rows where the requesting tenant is either the prior or the new owner. A tenant sees when they acquired a vehicle and when they divested one, but cannot read transfers between two third parties.
- **Audit immutability**. The history table's rows are immutable per the trigger; no application code path can rewrite history. Principle XVII's "audit is a feature, not a log" requirement is met at the history layer, where it matters.

### Part 3 — Atomic audit row on every transition

Every change to `tenant_vehicles` (`INSERT` or `UPDATE OF tenant_id`) fires a trigger that writes a `kind=vehicle_assignment_change` row to `audit_events` in the same transaction. The audit row's minimum field set (mirroring ADR-0007's break-glass pattern and ADR-0008's tenant-config-change pattern):

- `service_principal_subject` — the subject that authorized the assignment.
- `vehicle_id` — the affected vehicle.
- `prior_tenant_id` — NULL on initial provisioning.
- `new_tenant_id` — required.
- `reason_code` — from the documented enumeration.
- `correlation_id` — joins to the operator workflow that authorized the change.

The audit row is part of the same transaction as the `tenant_vehicles` write; a failing audit-row write aborts the entire transaction. Three atomic-audit applications in feature 002 (break-glass per ADR-0007; tenant-config-change per ADR-0008; vehicle-assignment-change per this ADR) follow the same pattern.

### Part 4 — Cache strategy: write-through Redis with TTL

The deployer hot path reads ownership per outbound deployment call. p99 < 5 ms is required to keep the SC-005 budget (feature-001 latency preserved within 10%).

Strategy: Redis-backed write-through cache keyed by `vehicle_id` storing `tenant_id`. Cache TTL: 1 hour (short enough that a missed invalidation expires quickly; long enough that the cache hit rate stays high under steady-state traffic). The deployer reads from the cache; on miss, reads from Postgres `tenant_vehicles` (which is the source of truth) and writes back to the cache. The service-principal write path (ownership transitions) invalidates the affected key explicitly.

Cache key shape: `vehicle_ownership:{vehicle_id} → {tenant_id}`. The key is global (not tenant-scoped) because the lookup answers "who owns this vehicle?", which is exactly the operator-level question the deployer needs. The RLS-tightened `tenant_vehicles` table is the authoritative store; the cache is a performance optimization.

Failure posture: on Redis unavailability, the deployer falls back to Postgres for every lookup. The fallback adds latency but does not break correctness. This is the opposite posture from rate limiting (which fails closed) because ownership lookup is a correctness gate, not a security primitive — the lookup MUST succeed to issue any deployment, and Postgres is the authoritative source.

### Part 5 — RLS posture on the ownership tables

`tenant_vehicles` enforces RESTRICTIVE RLS allowing tenant-scoped `SELECT` on the row's current owner only; service-principal-only writes (per ADR-0007's RESTRICTIVE pattern). A tenant reads their own current vehicles; cannot read another tenant's vehicles.

`tenant_vehicles_history` enforces RESTRICTIVE RLS allowing `SELECT` where the requesting tenant is either the prior or the new owner. A tenant reads transitions they participated in; cannot read transitions between two third parties. UPDATE and DELETE are denied for all principals (append-only).

Both tables' service-principal writes are routed through the same role used for `tenant_config` writes (ADR-0008): `collectmind_service_principal`. The role bypasses RLS via the standard Postgres `BYPASSRLS` privilege.

### Part 6 — Deployer hot-path integration

The deployer node, before any outbound `CollectorAIClient.deploy(...)` call:

1. For each `target_vehicle_id` in the policy:
   - Look up `vehicle_id → owning_tenant_id` via the cache.
   - If `owning_tenant_id != policy.tenant_id`, raise a Fatal error class.
2. On Fatal error:
   - Write a `kind=deployment_rejected` audit row carrying `policy_ref`, `target_vehicle_id`, `policy_declared_tenant_id`, `vehicle_owning_tenant_id` (operator-readable only), and the originating `correlation_id`.
   - Fire the page-tier alert `DeploymentTenantMismatch`.
   - Do NOT retry the deployment (the Fatal error class supersedes the deployer's existing Recoverable retry posture per Spec FR-022).
3. On success: proceed with the outbound deployment as in feature 001.

The lookup adds one Redis round trip (cache hit) or one Postgres query (cache miss) per deployment. SC-012 (page-tier alert within 60 s of mismatch) is honored by the existing Alertmanager routing.

## Consequences

### Positive

- Vehicle ownership matches operational reality (mutable, with explicit transition events). The application does not pretend the world is immutable when it isn't.
- The append-only history table satisfies Principle XVII's audit-queryability requirement at the level where it matters (the historical record), not at the level where it would break VIN semantics (the current-state row).
- The deployer-hot-path tenant validation is structurally consistent with the deployer's existing tenant-scoping check (the policy already carries `tenant_id`; this validation adds the vehicle-side check).
- The mutable-current-row + immutable-history pattern is the standard "kappa architecture" for state-with-history; well-understood by future maintainers.
- Two failure-mode postures (failure-closed for security primitives per ADR-0008; failure-open-with-degraded-mode for correctness gates here) are recorded explicitly. Operators do not need to guess which behavior applies where.

### Negative

- Two tables instead of one. The history table grows unbounded over time (one row per ownership transition × all vehicles). Vehicle re-sales are rare events; expected growth is ≪ 1 row/vehicle/year. A 10⁶-vehicle fleet produces ≪ 10⁶ history rows/year. Bounded, but not zero; an archival policy is a future-feature concern.
- The `tenant_vehicles_history` RLS policy lets a tenant detect that a vehicle was transferred away from them (the row appears with `prev_tenant_id == self, new_tenant_id != self`). The narrow leak (the requesting tenant learns *that some other tenant now owns the vehicle*, though not *which other tenant*) is acceptable; if a future feature wants stricter erasure, an ADR amendment is the vehicle.
- The Redis cache is a third write path (the existing hot-store writes + the rate-limit counter writes + the ownership-cache writes). Redis sizing must account for the additional namespace; the per-vehicle key cost is negligible (~ 100 bytes), so even a 10⁶-vehicle fleet adds ~100 MB to Redis working set.

### Neutral

- Vehicle decommissioning uses a sentinel `decommissioned` tenant identifier rather than row deletion, preserving foreign-key integrity from the policy registry and the telemetry hypertable.
- The `correlation_id` on `tenant_vehicles_history` joins to the `audit_events` row via the cross-table audit-traceability index; operators can reconstruct the complete operator workflow (HTTP request → audit row → DB transition) from the correlation id.

## Alternatives considered

### Strictly immutable assignment (immutable `tenant_vehicles`, no history table)

Rejected per Part 2. Breaks VIN semantics, breaks telemetry-history continuity, breaks policy lineage. The audit property an immutable model offers is achievable via the history table without paying these costs.

### Mutable current row WITHOUT history table (overwrite-in-place)

Rejected. Violates Principle XVII queryability. A tenant has no audit-trail visibility into when they acquired or divested a vehicle. The operator-side audit chain breaks entirely.

### Event-sourced ownership (current owner is a fold over the event log; no current-state table)

Rejected. Forces every deployer call to read N rows and fold them to determine the current owner. Turns a single-read hot path into a scan, breaking SC-005's latency-preservation budget. The current-state row + history-table shape is the materialized projection of the event-sourced model; we ship the projection directly because the hot path needs it.

### A separate microservice (e.g., a `vehicle-ownership-service` with its own datastore)

Rejected as over-decomposition. The lookup is a single index read on a single table; introducing a microservice for a single read adds network hops, deployment surface, and operational complexity for no win. Future features may justify the split (a federated multi-region ownership service?), but for feature 002 the colocated table is right.

### A graph database (e.g., Neo4j) for vehicle-tenant relationships

Rejected. The relationship is a flat 1:1 mapping; graph semantics buy nothing. Adding a new datastore would violate Principle II's "no mocked subsystems where a real one is feasible" by introducing infrastructure with no clear correctness benefit.

### Postgres-only lookup (no Redis cache)

Considered. Postgres can handle the deployer hot path at SC-005's budget if the table fits in shared_buffers (a 10⁶-row index easily does). The Redis cache adds operational complexity and a third write path. The win for caching is bounded: at 10⁶ vehicles × N deployments/second, Postgres absorbs the read load.

We ship the Redis cache anyway because (a) the existing hot-store + rate-limit counters already use Redis, so the namespace is already provisioned; (b) the cache decouples the deployer from Postgres availability for the duration of the cache TTL, which adds a small failure-mode safety margin; (c) the operational complexity is genuinely small (one cache invalidation hook on ownership writes). If operations finds the cache adds more pain than value, a future ADR can remove it without changing the data model.

## References

- [`specs/002-multi-tenant-isolation/spec.md`](../../specs/002-multi-tenant-isolation/spec.md) §US4, FR-021, FR-022, FR-023, FR-024, SC-012
- [`specs/002-multi-tenant-isolation/research.md`](../../specs/002-multi-tenant-isolation/research.md) §1
- [`specs/002-multi-tenant-isolation/data-model.md`](../../specs/002-multi-tenant-isolation/data-model.md) §New table: `tenant_vehicles` + `tenant_vehicles_history`
- ADR-0007 (RLS + break-glass) for the RESTRICTIVE RLS pattern reused on these tables
- ADR-0008 (rate limiting + audit-row patterns) for the atomic-audit transaction pattern reused on the `vehicle_assignment_change` kind
- Constitutional principles X, XVII, II at [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
