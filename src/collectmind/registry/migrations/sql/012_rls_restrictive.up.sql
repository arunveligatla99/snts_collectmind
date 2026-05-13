-- 012: tighten RLS from PERMISSIVE-only to PERMISSIVE-baseline + RESTRICTIVE-filter.
-- Feature 002 / ADR-0007 Part 1 / FR-001 / FR-002 / FR-003 / FR-004 / Principle X.
--
-- Postgres RLS semantics (load-bearing):
--   visible = (any permissive USING true) AND (every restrictive USING true)
-- If NO permissive policy exists, the implicit "no permissive matched" means NO rows are
-- visible to non-table-owner roles. So we keep a PERMISSIVE allow-all baseline AND add the
-- RESTRICTIVE per-tenant filter on top. The effective visibility:
--   (allow all rows) AND (rows matching app.tenant_id) = rows the current tenant owns.
--
-- This shape preserves the RESTRICTIVE missing-context + wrong-context defenses (the
-- RESTRICTIVE AND-combiner refuses rows when current_setting is NULL or mismatched) while
-- giving the policy engine a valid baseline-permissive set to AND against.

-- Drop the feature-001 permissive policies; we replace them with the baseline+restrictive pair.
DROP POLICY IF EXISTS tenants_permissive             ON tenants;
DROP POLICY IF EXISTS findings_permissive            ON diagnostic_findings;
DROP POLICY IF EXISTS vehicle_groups_permissive      ON vehicle_groups;
DROP POLICY IF EXISTS collection_policies_permissive ON collection_policies;
DROP POLICY IF EXISTS deployment_targets_permissive  ON deployment_targets;
DROP POLICY IF EXISTS policy_outcomes_permissive     ON policy_outcomes;
DROP POLICY IF EXISTS audit_events_permissive        ON audit_events;
DROP POLICY IF EXISTS telemetry_obs_permissive       ON telemetry_observations;
DROP POLICY IF EXISTS erasure_requests_permissive    ON erasure_requests;

-- PERMISSIVE baseline: allow all rows. The RESTRICTIVE filter below narrows visibility to
-- the current tenant's rows. Together they yield the per-tenant view.
CREATE POLICY tenants_permissive_baseline             ON tenants                FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY findings_permissive_baseline            ON diagnostic_findings    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY vehicle_groups_permissive_baseline      ON vehicle_groups         FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY collection_policies_permissive_baseline ON collection_policies    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY deployment_targets_permissive_baseline  ON deployment_targets     FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY policy_outcomes_permissive_baseline     ON policy_outcomes        FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY audit_events_permissive_baseline        ON audit_events           FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY telemetry_obs_permissive_baseline       ON telemetry_observations FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY erasure_requests_permissive_baseline    ON erasure_requests       FOR ALL USING (true) WITH CHECK (true);

-- RESTRICTIVE filter: rows must carry the current tenant's id; missing context refuses.
CREATE POLICY tenants_restrictive ON tenants AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY findings_restrictive ON diagnostic_findings AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY vehicle_groups_restrictive ON vehicle_groups AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY collection_policies_restrictive ON collection_policies AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY deployment_targets_restrictive ON deployment_targets AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY policy_outcomes_restrictive ON policy_outcomes AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY audit_events_restrictive ON audit_events AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY telemetry_obs_restrictive ON telemetry_observations AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  );

CREATE POLICY erasure_requests_restrictive ON erasure_requests AS RESTRICTIVE
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  )
  WITH CHECK (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND current_setting('app.tenant_id', true) <> ''
    AND tenant_id = current_setting('app.tenant_id', true)
  );
