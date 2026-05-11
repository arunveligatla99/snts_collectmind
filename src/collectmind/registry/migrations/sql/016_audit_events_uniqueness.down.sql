-- 016 rollback.
ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS audit_events_correlation_kind_unique;
