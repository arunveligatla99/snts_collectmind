-- 009: telemetry_observations. TimescaleDB hypertable; 90-day retention.
CREATE TABLE IF NOT EXISTS telemetry_observations (
  tenant_id    TEXT             NOT NULL REFERENCES tenants(tenant_id),
  vehicle_id   TEXT             NOT NULL CHECK (vehicle_id <> ''),
  signal_name  TEXT             NOT NULL CHECK (signal_name <> ''),
  value        DOUBLE PRECISION NOT NULL,
  observed_at  TIMESTAMPTZ      NOT NULL,
  policy_ref   JSONB,
  source       TEXT             NOT NULL CHECK (source IN ('simulator', 'real'))
);

SELECT create_hypertable(
  'telemetry_observations',
  'observed_at',
  chunk_time_interval => INTERVAL '1 day',
  if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS telemetry_obs_vehicle_observed_idx
  ON telemetry_observations (tenant_id, vehicle_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS telemetry_obs_signal_observed_idx
  ON telemetry_observations (tenant_id, signal_name, observed_at DESC);

SELECT add_retention_policy(
  'telemetry_observations',
  INTERVAL '90 days',
  if_not_exists => TRUE
);
