-- 012 rollback: revert to feature-001 PERMISSIVE-only policies.
DROP POLICY IF EXISTS tenants_restrictive             ON tenants;
DROP POLICY IF EXISTS findings_restrictive            ON diagnostic_findings;
DROP POLICY IF EXISTS vehicle_groups_restrictive      ON vehicle_groups;
DROP POLICY IF EXISTS collection_policies_restrictive ON collection_policies;
DROP POLICY IF EXISTS deployment_targets_restrictive  ON deployment_targets;
DROP POLICY IF EXISTS policy_outcomes_restrictive     ON policy_outcomes;
DROP POLICY IF EXISTS audit_events_restrictive        ON audit_events;
DROP POLICY IF EXISTS telemetry_obs_restrictive       ON telemetry_observations;
DROP POLICY IF EXISTS erasure_requests_restrictive    ON erasure_requests;

DROP POLICY IF EXISTS tenants_permissive_baseline             ON tenants;
DROP POLICY IF EXISTS findings_permissive_baseline            ON diagnostic_findings;
DROP POLICY IF EXISTS vehicle_groups_permissive_baseline      ON vehicle_groups;
DROP POLICY IF EXISTS collection_policies_permissive_baseline ON collection_policies;
DROP POLICY IF EXISTS deployment_targets_permissive_baseline  ON deployment_targets;
DROP POLICY IF EXISTS policy_outcomes_permissive_baseline     ON policy_outcomes;
DROP POLICY IF EXISTS audit_events_permissive_baseline        ON audit_events;
DROP POLICY IF EXISTS telemetry_obs_permissive_baseline       ON telemetry_observations;
DROP POLICY IF EXISTS erasure_requests_permissive_baseline    ON erasure_requests;

CREATE POLICY tenants_permissive             ON tenants                FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY findings_permissive            ON diagnostic_findings    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY vehicle_groups_permissive      ON vehicle_groups         FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY collection_policies_permissive ON collection_policies    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY deployment_targets_permissive  ON deployment_targets     FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY policy_outcomes_permissive     ON policy_outcomes        FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY audit_events_permissive        ON audit_events           FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY telemetry_obs_permissive       ON telemetry_observations FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY erasure_requests_permissive    ON erasure_requests       FOR ALL USING (true) WITH CHECK (true);
