-- 006: deployment_targets.
CREATE TABLE IF NOT EXISTS deployment_targets (
  deployment_id        TEXT        PRIMARY KEY CHECK (deployment_id <> ''),
  tenant_id            TEXT        NOT NULL REFERENCES tenants(tenant_id),
  policy_id            TEXT        NOT NULL,
  version              TEXT        NOT NULL CHECK (version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
  environment          TEXT        NOT NULL CHECK (environment IN ('dev', 'staging', 'prod')),
  vehicle_scope        JSONB       NOT NULL CHECK (jsonb_array_length(vehicle_scope) > 0),
  status               TEXT        NOT NULL CHECK (status IN ('requested', 'accepted', 'rejected', 'expired')),
  downstream_response  JSONB,
  requested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  accepted_at          TIMESTAMPTZ,
  expires_at           TIMESTAMPTZ,
  CONSTRAINT deployment_targets_policy_fk
    FOREIGN KEY (tenant_id, policy_id, version)
    REFERENCES collection_policies (tenant_id, policy_id, version)
);

CREATE INDEX IF NOT EXISTS deployment_targets_policy_idx
  ON deployment_targets (tenant_id, policy_id, version);

CREATE INDEX IF NOT EXISTS deployment_targets_status_expiry_idx
  ON deployment_targets (status, expires_at);
