-- 005: collection_policies. Immutable, semver-versioned, lineage-tagged.
CREATE TABLE IF NOT EXISTS collection_policies (
  tenant_id                       TEXT       NOT NULL REFERENCES tenants(tenant_id),
  policy_id                       TEXT       NOT NULL CHECK (policy_id <> ''),
  version                         TEXT       NOT NULL CHECK (version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
  signal_spec                     JSONB      NOT NULL CHECK (jsonb_typeof(signal_spec) = 'array' AND jsonb_array_length(signal_spec) > 0),
  trigger_conditions              JSONB      NOT NULL CHECK (jsonb_typeof(trigger_conditions) = 'array'),
  collection_window_hours_logical INTEGER    NOT NULL CHECK (collection_window_hours_logical BETWEEN 1 AND 168),
  vehicle_scope                   JSONB      NOT NULL CHECK (jsonb_array_length(vehicle_scope) > 0),
  hypothesis_statement            TEXT       NOT NULL,
  data_governance_flags           JSONB      NOT NULL,
  confidence_threshold            NUMERIC(4,3) NOT NULL CHECK (confidence_threshold BETWEEN 0.000 AND 1.000),
  generated_from_session_id       TEXT       NOT NULL CHECK (generated_from_session_id <> ''),
  originating_finding             JSONB      NOT NULL,
  prompt_template_version         TEXT       NOT NULL CHECK (prompt_template_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
  slm_repo                        TEXT       NOT NULL,
  slm_revision_sha                TEXT       NOT NULL CHECK (length(slm_revision_sha) = 40),
  slm_runtime                     TEXT       NOT NULL CHECK (slm_runtime IN ('vllm', 'llama_cpp', 'stub')),
  slm_runtime_version             TEXT       NOT NULL,
  slm_quantization                TEXT       NOT NULL CHECK (slm_quantization IN ('bf16', 'gguf-q4_k_m', 'none')),
  slm_decoding_seed               BIGINT     NOT NULL,
  payload_signature               BYTEA      NOT NULL,
  signature_key_id                TEXT       NOT NULL,
  created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, policy_id, version)
);

CREATE INDEX IF NOT EXISTS collection_policies_tenant_policy_created_idx
  ON collection_policies (tenant_id, policy_id, created_at DESC);

CREATE INDEX IF NOT EXISTS collection_policies_signal_spec_idx
  ON collection_policies USING GIN (signal_spec);

CREATE INDEX IF NOT EXISTS collection_policies_trigger_conditions_idx
  ON collection_policies USING GIN (trigger_conditions);

-- Reject UPDATE and DELETE outside the erasure path. The erasure dispatcher disables
-- this trigger via SET LOCAL collectmind.erasure = 'on' inside its transaction.
CREATE OR REPLACE FUNCTION reject_mutation_unless_erasure() RETURNS trigger AS $$
BEGIN
  IF current_setting('collectmind.erasure', true) <> 'on' THEN
    RAISE EXCEPTION 'collection_policies are immutable; mutation rejected';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER collection_policies_immutable
  BEFORE UPDATE OR DELETE ON collection_policies
  FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_erasure();
