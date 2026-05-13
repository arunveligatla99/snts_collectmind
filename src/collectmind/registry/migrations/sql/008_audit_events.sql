-- 008: audit_events. Immutable. FR-017a minimum field set.
CREATE TABLE IF NOT EXISTS audit_events (
  event_id                  TEXT        PRIMARY KEY CHECK (event_id <> ''),
  tenant_id                 TEXT        NOT NULL REFERENCES tenants(tenant_id),
  kind                      TEXT        NOT NULL CHECK (kind IN ('accepted', 'rejected', 'generated', 'validated', 'deployed', 'outcome', 'erasure')),
  originating_finding       JSONB,
  policy_ref                JSONB,
  deployment_ref            JSONB,
  outcome_ref               JSONB,
  slm_repo                  TEXT,
  slm_revision_sha          TEXT,
  slm_runtime               TEXT,
  slm_runtime_version       TEXT,
  slm_quantization          TEXT,
  slm_decoding_seed         BIGINT,
  prompt_template_version   TEXT,
  inbound_schema_version    TEXT,
  time_acceleration_factor  NUMERIC(10,3),
  principal_subject         TEXT        NOT NULL CHECK (principal_subject <> ''),
  correlation_id            TEXT        NOT NULL CHECK (correlation_id <> ''),
  occurred_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Generated audit events MUST carry the full SLM/prompt/seed set per FR-017a.
  CHECK (
    kind <> 'generated' OR (
      slm_repo IS NOT NULL
      AND slm_revision_sha IS NOT NULL
      AND slm_runtime IS NOT NULL
      AND slm_runtime_version IS NOT NULL
      AND slm_quantization IS NOT NULL
      AND slm_decoding_seed IS NOT NULL
      AND prompt_template_version IS NOT NULL
    )
  )
);

CREATE INDEX IF NOT EXISTS audit_events_finding_idx
  ON audit_events USING GIN (originating_finding);

CREATE INDEX IF NOT EXISTS audit_events_tenant_kind_occurred_idx
  ON audit_events (tenant_id, kind, occurred_at DESC);

CREATE INDEX IF NOT EXISTS audit_events_correlation_idx
  ON audit_events (correlation_id);

CREATE TRIGGER audit_events_immutable
  BEFORE UPDATE OR DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_erasure();
