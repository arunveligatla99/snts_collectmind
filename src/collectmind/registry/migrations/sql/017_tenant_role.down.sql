-- 017 rollback: drop the tenant role and its grants.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM collectmind_tenant;

REVOKE collectmind_tenant FROM collectmind;

REVOKE SELECT, INSERT, UPDATE, DELETE ON
  tenants, diagnostic_findings, vehicle_groups, collection_policies, deployment_targets,
  policy_outcomes, audit_events, telemetry_observations, erasure_requests,
  tenant_config, tenant_vehicles, tenant_vehicles_history
FROM collectmind_tenant;

REVOKE USAGE ON ALL SEQUENCES IN SCHEMA public FROM collectmind_tenant;
REVOKE USAGE ON SCHEMA public FROM collectmind_tenant;

DROP ROLE IF EXISTS collectmind_tenant;
