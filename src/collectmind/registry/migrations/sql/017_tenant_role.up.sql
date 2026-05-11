-- 017: provision the non-BYPASSRLS tenant role used by tenant-scoped request handlers.
-- Feature 002 / ADR-0007 Part 1 + Part 3.
--
-- Two-role model:
--   * `collectmind` (existing superuser, BYPASSRLS by default): used by the migration runner,
--     the service-principal write primitives (break-glass / tenant_config / tenant_vehicles),
--     and any process that legitimately needs to bypass RLS. Owns every table.
--   * `collectmind_tenant` (NEW, non-BYPASSRLS): used by every tenant-scoped request handler.
--     Inherits SELECT/INSERT/UPDATE/DELETE on every tenant-scoped table. Subject to the
--     RESTRICTIVE RLS policies in migration 012.
--
-- The orchestration-api connects as `collectmind` and uses `SET LOCAL ROLE collectmind_tenant`
-- inside `Database.acquire(tenant_id)` to drop into the non-BYPASSRLS role for the duration of
-- the transaction. `SET LOCAL ROLE` requires the calling role to be a member of the target
-- role; the GRANT MEMBERSHIP below provides that. On COMMIT/ROLLBACK the role reverts to the
-- session role (`collectmind`), and `app.tenant_id` reverts to NULL (per `SET LOCAL`).

-- Create the role idempotently.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'collectmind_tenant') THEN
    CREATE ROLE collectmind_tenant NOLOGIN;
  END IF;
END
$$;

-- Grant SELECT/INSERT/UPDATE/DELETE on every tenant-scoped table.
GRANT USAGE ON SCHEMA public TO collectmind_tenant;
GRANT SELECT, INSERT, UPDATE, DELETE ON
  tenants,
  diagnostic_findings,
  vehicle_groups,
  collection_policies,
  deployment_targets,
  policy_outcomes,
  audit_events,
  telemetry_observations,
  erasure_requests,
  tenant_config,
  tenant_vehicles,
  tenant_vehicles_history
TO collectmind_tenant;

GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO collectmind_tenant;

-- Allow `collectmind` to SET ROLE collectmind_tenant (required for SET LOCAL ROLE).
GRANT collectmind_tenant TO collectmind;

-- Default privileges on future tables: collectmind_tenant gets the standard CRUD bundle.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO collectmind_tenant;
