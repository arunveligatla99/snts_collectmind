# Data Model: Multi-Tenant Isolation

**Feature**: `002-multi-tenant-isolation`
**Date**: 2026-05-11
**Status**: Phase 1 — extends the feature-001 data model with three new tables (`tenant_config`, `tenant_vehicles`, `tenant_vehicles_history`), tightens RLS on every existing tenant-scoped table, and extends the `audit_events` `kind` enumeration with four new values.

This file is the source of truth for the new schema in this feature. Concrete SQL ships under `src/collectmind/registry/migrations/sql/`; this file describes the intent and invariants those migrations enforce.

## RLS hardening of existing tables (FR-001 / FR-004)

Every tenant-scoped table that ships from feature 001 transitions from `PERMISSIVE` to `RESTRICTIVE` policy mode in migration `011_rls_restrictive.up.sql`. The migration is rollbackable via `011_rls_restrictive.down.sql` (RESTRICTIVE → PERMISSIVE), tested in both directions by `tests/integration/test_rls_migration_rollback.py` against the SC-010 ≤30s budget.

Tables affected:
- `tenants` (the tenants directory itself; not RLS-protected — readable by every authenticated principal for their own row; service-principal-only writes).
- `diagnostic_findings`
- `collection_policies`
- `deployment_targets`
- `policy_outcomes`
- `audit_events`
- `telemetry_observations` (TimescaleDB hypertable)
- `erasure_requests`
- `tenant_config` (NEW; see below)
- `tenant_vehicles` (NEW; see below)
- `tenant_vehicles_history` (NEW; see below)

For each table, the migration:
1. Drops the existing `PERMISSIVE` policy.
2. Creates a new `RESTRICTIVE` policy that enforces both:
   - **Missing-context defense**: `current_setting('app.tenant_id', true) IS NOT NULL` (the third arg `true` returns NULL on missing setting rather than raising; the policy refuses to match when NULL).
   - **Wrong-context defense**: `tenant_id = current_setting('app.tenant_id', true)::TEXT`.
3. Adds a `WITH CHECK` clause on `INSERT`/`UPDATE` that ensures the row's `tenant_id` matches the session GUC, refusing cross-tenant writes from inside a tenant context.
4. Verifies the policy via a fixture migration test that asserts a session with no GUC returns zero rows on `SELECT *`.

### Connection-pool transaction-boundary contract

Per the Spec Edge Case 3 ("a long-running database transaction is opened and the connection is reused across requests with different tenant identifiers: the Row-Level Security context MUST be re-established on every transaction boundary; an attempt to reuse a stale context MUST fail closed"), the `Database.acquire(tenant_id)` context manager MUST issue `SET LOCAL app.tenant_id = $tenant_id` at the **start of every transaction**, not at connection-checkout time. `SET LOCAL` is scoped to the current transaction; on transaction commit/rollback the setting reverts to NULL, leaving the next transaction's first SELECT to read NULL and (per the missing-context defense) return zero rows until the next `SET LOCAL` lands. This is the failure-closed property; tested by `tests/integration/test_rls_restrictive.py::test_stale_gucs_fail_closed`.

## New table: `tenant_config`

Per-tenant rate-limit overrides for FR-013 / FR-013a / FR-013b. Created in migration `012_tenant_config.up.sql`.

```
tenant_config
─────────────────────────────────────────────────────────────────────────────────
tenant_id                  TEXT PRIMARY KEY
inbound_sustained_rps      INTEGER NOT NULL    -- requests per second sustained for POST /api/v1/findings
inbound_burst_capacity     INTEGER NOT NULL    -- token-bucket burst capacity for the inbound endpoint
query_sustained_rps        INTEGER NOT NULL    -- requests per second sustained for GET /api/v1/...
query_burst_capacity       INTEGER NOT NULL    -- token-bucket burst capacity for query endpoints
updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
updated_by_subject         TEXT NOT NULL       -- service principal that wrote the row

CONSTRAINTS
- inbound_sustained_rps  > 0
- inbound_burst_capacity >= inbound_sustained_rps
- query_sustained_rps    > 0
- query_burst_capacity   >= query_sustained_rps
- updated_by_subject     != ''

RLS (RESTRICTIVE):
- SELECT  : tenant_id = current_setting('app.tenant_id', true)         -- tenants read OWN row only (FR-013a)
- INSERT  : DENY for non-service principals
- UPDATE  : DENY for non-service principals
- DELETE  : DENY for non-service principals
- Service-principal connection bypasses RLS via a separate Postgres role; writes happen only through this role.

TRIGGER: tenant_config_change_audit_trigger
- AFTER INSERT/UPDATE/DELETE on tenant_config
- Writes a `kind=tenant_config_change` row to audit_events in the same transaction (FR-013b)
- Audit row minimum field set: service_principal_subject, target_tenant_id, prior_values (NULL on INSERT), new_values (NULL on DELETE), correlation_id
- On audit-write failure the trigger raises; the outer transaction rolls back; the tenant_config write is reverted.

TRIGGER: tenant_config_notify_trigger
- AFTER INSERT/UPDATE/DELETE on tenant_config
- Emits NOTIFY tenant_config_changed, '<tenant_id>'
- Consumed by the in-process LISTEN consumer in src/collectmind/ratelimit/config_cache.py
- TTL fallback (5 s) covers NOTIFY-pipeline loss; see research §5b.
```

When no `tenant_config` row exists for a tenant, the in-process cache returns the FR-012 defaults: inbound 2000 / burst 4000; query 200 / burst 400. The defaults live as constants in `src/collectmind/ratelimit/defaults.py` and are referenced from `tests/unit/test_ratelimit_defaults.py` for parity with FR-012.

## New table: `tenant_vehicles` + `tenant_vehicles_history`

The canonical Tenant-Vehicle Ownership store called out in [`research.md`](./research.md) §1 and recorded in ADR-0009. Created in migration `013_tenant_vehicles.up.sql`.

### `tenant_vehicles` — current ownership (one row per vehicle)

```
tenant_vehicles
─────────────────────────────────────────────────────────────────────────────────
vehicle_id                 TEXT PRIMARY KEY                       -- VIN-like opaque identifier; unique within the system, not just within tenant
tenant_id                  TEXT NOT NULL                          -- current owning tenant
assigned_at                TIMESTAMPTZ NOT NULL DEFAULT now()
assigned_by_subject        TEXT NOT NULL                          -- operator subject that authorized the current assignment
reason_code                TEXT NOT NULL                          -- enum: 'initial_provisioning' | 'resale' | 'fleet_reassignment' | 'oem_handoff' | 'lease_return' | 'totaled' | 'other'

CONSTRAINTS
- assigned_by_subject != ''
- reason_code IN ('initial_provisioning', 'resale', 'fleet_reassignment', 'oem_handoff', 'lease_return', 'totaled', 'other')

RLS (RESTRICTIVE):
- SELECT  : tenant_id = current_setting('app.tenant_id', true)        -- tenant reads its own vehicle assignments only
- INSERT  : DENY for non-service principals
- UPDATE  : DENY for non-service principals
- DELETE  : DENY for non-service principals (vehicles are not deleted; transferred to a sentinel tenant 'decommissioned' instead)

TRIGGER: tenant_vehicles_history_trigger
- BEFORE INSERT OR UPDATE OF tenant_id on tenant_vehicles
- Appends a row to tenant_vehicles_history capturing the transition

TRIGGER: tenant_vehicles_audit_trigger
- AFTER INSERT OR UPDATE OF tenant_id on tenant_vehicles
- Writes a `kind=vehicle_assignment_change` row to audit_events in the same transaction
- Audit row minimum field set: service_principal_subject, vehicle_id, prior_tenant_id (NULL on INSERT), new_tenant_id, reason_code, correlation_id
```

### `tenant_vehicles_history` — append-only transfer log

```
tenant_vehicles_history
─────────────────────────────────────────────────────────────────────────────────
history_id                 BIGSERIAL PRIMARY KEY
vehicle_id                 TEXT NOT NULL
prev_tenant_id             TEXT                                   -- NULL on initial provisioning
new_tenant_id              TEXT NOT NULL
operator_subject           TEXT NOT NULL
reason_code                TEXT NOT NULL                          -- same enum as tenant_vehicles.reason_code
transition_at              TIMESTAMPTZ NOT NULL DEFAULT now()
correlation_id             TEXT NOT NULL                          -- joins to audit_events row for cross-table audit traceability

INDEX: tenant_vehicles_history_vehicle_idx ON (vehicle_id, transition_at)
INDEX: tenant_vehicles_history_prev_idx    ON (prev_tenant_id, transition_at)
INDEX: tenant_vehicles_history_new_idx     ON (new_tenant_id, transition_at)

RLS (RESTRICTIVE):
- SELECT  : prev_tenant_id = current_setting('app.tenant_id', true)
           OR new_tenant_id = current_setting('app.tenant_id', true)
- INSERT  : Only via the tenant_vehicles_history_trigger; no other writer.
- UPDATE  : DENY for all principals (append-only).
- DELETE  : DENY for all principals (append-only).

IMMUTABILITY: enforced by row-level trigger that raises on any UPDATE or DELETE attempt; same pattern as the audit_events immutability trigger from feature 001.
```

A tenant reading `tenant_vehicles_history` sees rows where they were either the prior or the new owner; never rows between two third parties. The erasure dispatcher (feature 001 FR-020a) is extended in this feature to redact the `operator_subject` column when an erasure request is processed for the operator's tenant (the operator subject is not tenant PII per se but the broader pattern is to redact rather than delete; the historical fact survives).

## Extended `audit_events.kind` enumeration

Feature 001 ships four audit-row kinds: `generated`, `validated`, `deployed`, `outcome`. This feature adds four more:

- `break_glass` — FR-005b. Written by the break-glass query primitive in the same transaction as the bypassed `audit_events` SELECT.
- `tenant_config_change` — FR-013b. Written by the `tenant_config_change_audit_trigger`.
- `deployment_rejected` — FR-023. Written by the deployer node when a tenant-vehicle ownership lookup mismatches the policy's declared tenant.
- `vehicle_assignment_change` — written by the `tenant_vehicles_audit_trigger` on every change to `tenant_vehicles`.

For each new kind, the audit row's `_extras` JSONB field (the feature-001 audit primitive) carries the kind-specific minimum field set, asserted by a unit-tier test per kind in `tests/unit/test_audit_kinds.py`. The minimum field sets are:

| Kind | Required fields |
|---|---|
| `break_glass` | `operator_principal_subject`, `tenant_scope`, `reason_code`, `correlation_id` |
| `tenant_config_change` | `service_principal_subject`, `target_tenant_id`, `prior_values`, `new_values`, `correlation_id` |
| `deployment_rejected` | `policy_ref`, `target_vehicle_id`, `policy_declared_tenant_id`, `vehicle_owning_tenant_id`, `correlation_id` (the *owning* tenant id is operator-readable only; the requesting tenant never sees it because the response shape is 404) |
| `vehicle_assignment_change` | `service_principal_subject`, `vehicle_id`, `prior_tenant_id`, `new_tenant_id`, `reason_code`, `correlation_id` |

The feature-001 deferral (Flag 9: `UNIQUE (correlation_id, kind)` constraint on `audit_events`) lands in this feature's migration `014_audit_events_uniqueness.up.sql` because the new audit-row kinds make idempotency genuinely load-bearing (a retried break-glass query or a retried tenant-config write must not produce duplicate audit rows). The migration adds the unique constraint plus an `ON CONFLICT DO NOTHING` clause to the audit writer.

The feature-001 deferral (Flag 10: dedicated `error JSONB` column) is **NOT** landed in this feature; it remains in `docs/PROJECT_STATE.md`'s deferred list. The new audit-row kinds do not use the error column.

## Audit-event lineage chains

The four feature-001 kinds form the `generated` → `validated` → `deployed` → `outcome` chain per finding. The four new kinds in this feature are stand-alone events, not part of the per-finding chain:

- `break_glass`: keyed by `correlation_id` (the operator's chosen identifier for the incident).
- `tenant_config_change`: keyed by the configuration write's correlation_id.
- `deployment_rejected`: keyed by the **originating finding's correlation_id** so it joins to `generated`/`validated` for the rejected policy.
- `vehicle_assignment_change`: keyed by a fresh correlation_id minted by the service-principal write call.

The audit-query API (in scope for feature 002 only via the break-glass primitive) returns events grouped by correlation_id; the regular `GET /api/v1/audit/{cid}` endpoint serves only the original four kinds plus `deployment_rejected` (which references a finding under the requesting tenant's scope and is therefore tenant-readable). The other three new kinds (`break_glass`, `tenant_config_change`, `vehicle_assignment_change`) are operator-only: the regular audit-query handler filters them out by `kind NOT IN (...)`; the break-glass handler returns them under operator audience.

## Migration order

```
011_rls_restrictive.up.sql      -- tighten RLS on every existing tenant-scoped table
012_tenant_config.up.sql        -- new table + triggers + LISTEN/NOTIFY channel
013_tenant_vehicles.up.sql      -- new tables + triggers + history immutability
014_audit_events_uniqueness.up.sql  -- UNIQUE (correlation_id, kind) constraint
```

Migrations are applied in order by the existing `src/collectmind/registry/migrations/runner.py` migrator. Each `*.up.sql` has a paired `*.down.sql`; the down migrations reverse the schema changes in reverse order. The migration suite test (`tests/integration/test_rls_migration_rollback.py`) drives forward + backward against a fresh testcontainer Postgres and asserts both directions complete in ≤30s (SC-010).

## Schema-evolution invariants

- No existing table column is dropped or renamed in this feature; only triggers, policies, and new tables are added. Feature-001 contracts remain valid.
- The `audit_events` row shape is unchanged; only the `kind` enumeration grows. The OpenAPI `AuditEvent` schema picks up four new enum values; the breaking-change policy says enum-only additions are minor version bumps; both `orchestration-api.v1.yaml` and `query-api.v1.yaml` bump to `v1.1.0`.
- The `tenant_id` data type stays `TEXT` throughout, matching feature 001. No widening to UUID-or-bigint.
- TimescaleDB hypertable on `telemetry_observations` is unaffected by the RLS tightening (RLS policies apply to hypertables as if they were regular tables under recent TimescaleDB versions); the hot-store key shape change is orthogonal to the hypertable.

## Open question (deferred to /speckit-implement)

- The migration applies `RESTRICTIVE` policies in a single transaction per table; **rolling-deploy compatibility** (mixed-fleet of orchestration-api containers, some on the PERMISSIVE policy and some on the RESTRICTIVE) is in scope but tested only at the migration boundary, not in the steady-state. The RESTRICTIVE policies are a strict superset of the PERMISSIVE policies (every row visible under RESTRICTIVE is visible under PERMISSIVE), so a mixed fleet during the rolling deploy degrades to "some requests see fewer rows than they would post-rollout" — never to "some requests see rows they shouldn't." Forward migration is therefore safe under rolling deploy; backward migration is also safe (RESTRICTIVE → PERMISSIVE widens visibility, never narrows). Tests `tests/integration/test_rls_migration_rollback.py` assert this property explicitly.
