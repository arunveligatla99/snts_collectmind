-- 007: policy_outcomes.
CREATE TABLE IF NOT EXISTS policy_outcomes (
  outcome_id              TEXT        PRIMARY KEY CHECK (outcome_id <> ''),
  tenant_id               TEXT        NOT NULL REFERENCES tenants(tenant_id),
  originating_finding     JSONB       NOT NULL,
  policy_id               TEXT        NOT NULL,
  version                 TEXT        NOT NULL CHECK (version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
  hypothesis_state        TEXT        NOT NULL CHECK (hypothesis_state IN ('confirmed', 'ruled_out', 'no_data')),
  evaluated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  evidence_summary        JSONB       NOT NULL DEFAULT '{}'::jsonb,
  signals_collected_count INTEGER     NOT NULL DEFAULT 0 CHECK (signals_collected_count >= 0),
  data_quality_score      NUMERIC(4,3) NOT NULL DEFAULT 0.000 CHECK (data_quality_score BETWEEN 0.000 AND 1.000),
  CONSTRAINT policy_outcomes_policy_fk
    FOREIGN KEY (tenant_id, policy_id, version)
    REFERENCES collection_policies (tenant_id, policy_id, version)
);

CREATE INDEX IF NOT EXISTS policy_outcomes_finding_idx
  ON policy_outcomes USING GIN (originating_finding);

CREATE INDEX IF NOT EXISTS policy_outcomes_state_evaluated_idx
  ON policy_outcomes (tenant_id, hypothesis_state, evaluated_at DESC);
