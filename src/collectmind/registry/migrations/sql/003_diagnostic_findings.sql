-- 003: diagnostic_findings. Composite PK (tenant_id, finding_id) per Spec Clarifications Q1.
CREATE TABLE IF NOT EXISTS diagnostic_findings (
  tenant_id                 TEXT      NOT NULL REFERENCES tenants(tenant_id),
  finding_id                TEXT      NOT NULL CHECK (finding_id <> ''),
  schema_version            TEXT      NOT NULL CHECK (schema_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
  anomaly_type              TEXT      NOT NULL,
  hypothesis_class          TEXT      NOT NULL CHECK (hypothesis_class <> ''),
  hypothesis_statement      TEXT      NOT NULL CHECK (length(hypothesis_statement) BETWEEN 1 AND 4096),
  candidate_signals         JSONB     NOT NULL CHECK (jsonb_array_length(candidate_signals) > 0),
  vehicle_scope             JSONB     NOT NULL CHECK (jsonb_array_length(vehicle_scope) > 0),
  upstream_confidence       NUMERIC(4,3) NOT NULL CHECK (upstream_confidence BETWEEN 0.000 AND 1.000),
  received_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  received_payload_sha256   BYTEA     NOT NULL CHECK (length(received_payload_sha256) = 32),
  PRIMARY KEY (tenant_id, finding_id)
);

CREATE INDEX IF NOT EXISTS diagnostic_findings_tenant_received_idx
  ON diagnostic_findings (tenant_id, received_at DESC);

CREATE INDEX IF NOT EXISTS diagnostic_findings_class_anomaly_idx
  ON diagnostic_findings (hypothesis_class, anomaly_type);
