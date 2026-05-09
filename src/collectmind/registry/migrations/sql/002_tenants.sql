-- 002: tenants. Single-tenant in feature 001; the schema is multi-tenant from day one.
CREATE TABLE IF NOT EXISTS tenants (
  tenant_id        TEXT PRIMARY KEY CHECK (tenant_id <> ''),
  display_name     TEXT NOT NULL CHECK (display_name <> ''),
  oauth2_issuer    TEXT NOT NULL CHECK (oauth2_issuer <> ''),
  oauth2_audience  TEXT NOT NULL CHECK (oauth2_audience <> ''),
  status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO tenants (tenant_id, display_name, oauth2_issuer, oauth2_audience)
VALUES (
  'feature-001-default',
  'Feature 001 Default Tenant',
  'http://mock-issuer:8088',
  'collectmind-api'
)
ON CONFLICT (tenant_id) DO NOTHING;
