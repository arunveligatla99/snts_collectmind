-- 010: erasure_requests. GDPR/CCPA right-to-erasure (FR-020a).
CREATE TABLE IF NOT EXISTS erasure_requests (
  request_id            TEXT        PRIMARY KEY CHECK (request_id <> ''),
  tenant_id             TEXT        NOT NULL REFERENCES tenants(tenant_id),
  subject_kind          TEXT        NOT NULL CHECK (subject_kind IN ('vehicle', 'finding', 'principal')),
  subject_identifier    TEXT        NOT NULL CHECK (subject_identifier <> ''),
  requested_by          TEXT        NOT NULL CHECK (requested_by <> ''),
  requested_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  target_completion_at  TIMESTAMPTZ NOT NULL,
  status                TEXT        NOT NULL DEFAULT 'requested' CHECK (status IN ('requested', 'in_progress', 'completed', 'partial')),
  per_store_status      JSONB       NOT NULL DEFAULT '{}'::jsonb,
  mode                  TEXT        NOT NULL DEFAULT 'erased' CHECK (mode IN ('erased', 'redacted')),
  completed_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS erasure_requests_tenant_status_idx
  ON erasure_requests (tenant_id, status, requested_at DESC);
