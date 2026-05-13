-- 016: UNIQUE (correlation_id, kind) on audit_events.
-- Closes feature-001 Flag 9 deferral (docs/DECISIONS.md 2026-05-09).
-- Audit writer applies ON CONFLICT DO NOTHING for retry idempotency.
-- Principle XVII.

ALTER TABLE audit_events ADD CONSTRAINT audit_events_correlation_kind_unique
  UNIQUE (correlation_id, kind);
