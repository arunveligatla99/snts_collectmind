-- 011: enable RLS. Permissive policies in feature 001; feature 002 tightens these.
ALTER TABLE tenants                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE diagnostic_findings      ENABLE ROW LEVEL SECURITY;
ALTER TABLE vehicle_groups           ENABLE ROW LEVEL SECURITY;
ALTER TABLE collection_policies      ENABLE ROW LEVEL SECURITY;
ALTER TABLE deployment_targets       ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_outcomes          ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events             ENABLE ROW LEVEL SECURITY;
ALTER TABLE telemetry_observations   ENABLE ROW LEVEL SECURITY;
ALTER TABLE erasure_requests         ENABLE ROW LEVEL SECURITY;

-- Permissive feature-001 policy: every authenticated session sees every row.
-- Feature 002 replaces these with restrictive USING/CHECK clauses bound to app.tenant_id.
CREATE POLICY tenants_permissive             ON tenants                FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY findings_permissive            ON diagnostic_findings    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY vehicle_groups_permissive      ON vehicle_groups         FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY collection_policies_permissive ON collection_policies    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY deployment_targets_permissive  ON deployment_targets     FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY policy_outcomes_permissive     ON policy_outcomes        FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY audit_events_permissive        ON audit_events           FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY telemetry_obs_permissive       ON telemetry_observations FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY erasure_requests_permissive    ON erasure_requests       FOR ALL USING (true) WITH CHECK (true);
