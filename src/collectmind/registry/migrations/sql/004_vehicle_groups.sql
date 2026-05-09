-- 004: vehicle_groups.
CREATE TABLE IF NOT EXISTS vehicle_groups (
  tenant_id    TEXT      NOT NULL REFERENCES tenants(tenant_id),
  group_id     TEXT      NOT NULL CHECK (group_id <> ''),
  vehicle_ids  JSONB     NOT NULL CHECK (jsonb_array_length(vehicle_ids) > 0),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, group_id)
);
