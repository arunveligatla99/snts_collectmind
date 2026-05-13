-- 013: widen audit_events.kind CHECK constraint with four new kinds shipped by feature 002.
-- Prerequisite for every subsequent migration that fires an atomic-audit trigger.
-- FR-005b / FR-013b / FR-023 / Principle XVII.

ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS audit_events_kind_check;
ALTER TABLE audit_events ADD CONSTRAINT audit_events_kind_check
  CHECK (kind IN (
    'accepted', 'rejected', 'generated', 'validated', 'deployed', 'outcome', 'erasure',
    'break_glass', 'tenant_config_change', 'deployment_rejected', 'vehicle_assignment_change'
  ));
