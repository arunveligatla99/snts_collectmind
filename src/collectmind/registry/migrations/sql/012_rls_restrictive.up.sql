-- 012: tighten RLS from PERMISSIVE to RESTRICTIVE on every tenant-scoped table.
-- Feature 002 / ADR-0007 / FR-001 / FR-002 / FR-003 / FR-004 / Principle X.
--
-- Each new policy enforces both defenses:
--   missing-context: current_setting('app.tenant_id', true) IS NOT NULL
--   wrong-context:   tenant_id = current_setting('app.tenant_id', true)::TEXT
--
-- WITH CHECK on INSERT/UPDATE refuses cross-tenant writes from inside a tenant context.
--
-- RESTRICTIVE policies are a strict superset of PERMISSIVE visibility per ADR-0007 Part 2:
-- rolling-deploy safe in both directions without a feature flag.

-- Drop feature-001 permissive policies.
DROP POLICY IF EXISTS tenants_permissive             ON tenants;
DROP POLICY IF EXISTS findings_permissive            ON diagnostic_findings;
DROP POLICY IF EXISTS vehicle_groups_permissive      ON vehicle_groups;
DROP POLICY IF EXISTS collection_policies_permissive ON collection_policies;
DROP POLICY IF EXISTS deployment_targets_permissive  ON deployment_targets;
DROP POLICY IF EXISTS policy_outcomes_permissive     ON policy_outcomes;
DROP POLICY IF EXISTS audit_events_permissive        ON audit_events;
DROP POLICY IF EXISTS telemetry_obs_permissive       ON telemetry_observations;
DROP POLICY IF EXISTS erasure_requests_permissive    ON erasure_requests;

-- Create RESTRICTIVE policies. Policy mode 'RESTRICTIVE' AND-combines with any future PERMISSIVE policy.
CREATE POLICY tenants_restrictive ON tenants AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY findings_restrictive ON diagnostic_findings AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY vehicle_groups_restrictive ON vehicle_groups AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY collection_policies_restrictive ON collection_policies AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY deployment_targets_restrictive ON deployment_targets AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY policy_outcomes_restrictive ON policy_outcomes AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY audit_events_restrictive ON audit_events AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY telemetry_obs_restrictive ON telemetry_observations AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY erasure_requests_restrictive ON erasure_requests AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  );
