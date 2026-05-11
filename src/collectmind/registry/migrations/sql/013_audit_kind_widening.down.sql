-- 013 rollback: narrow audit_events.kind CHECK constraint to feature-001 kinds.
-- WARNING: if any rows of the new kinds exist, the ALTER will fail. Operator must
-- redact or remove those rows before rollback. Per ADR-0007 Part 2 the migration
-- pair is bidirectional; this rollback is intentionally strict to surface the
-- "you have new-kind rows that would orphan if the constraint narrows" case.

ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS audit_events_kind_check;
ALTER TABLE audit_events ADD CONSTRAINT audit_events_kind_check
  CHECK (kind IN (
    'accepted', 'rejected', 'generated', 'validated', 'deployed', 'outcome', 'erasure'
  ));
