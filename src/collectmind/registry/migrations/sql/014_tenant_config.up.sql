-- 014: tenant_config per-tenant rate-limit overrides.
-- Feature 002 / ADR-0008 / FR-013 / FR-013a / FR-013b / SC-014.

CREATE TABLE IF NOT EXISTS tenant_config (
  tenant_id              TEXT PRIMARY KEY REFERENCES tenants(tenant_id),
  inbound_sustained_rps  INTEGER NOT NULL CHECK (inbound_sustained_rps > 0),
  inbound_burst_capacity INTEGER NOT NULL CHECK (inbound_burst_capacity >= inbound_sustained_rps),
  query_sustained_rps    INTEGER NOT NULL CHECK (query_sustained_rps > 0),
  query_burst_capacity   INTEGER NOT NULL CHECK (query_burst_capacity >= query_sustained_rps),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by_subject     TEXT NOT NULL CHECK (updated_by_subject <> '')
);

ALTER TABLE tenant_config ENABLE ROW LEVEL SECURITY;

-- RESTRICTIVE per FR-013a: tenant-scoped SELECT for own row only.
-- Non-service principals are denied INSERT/UPDATE/DELETE by absence of any permissive
-- policy (RLS default = deny). Service-principal connections bypass RLS via BYPASSRLS.
CREATE POLICY tenant_config_restrictive_select ON tenant_config AS RESTRICTIVE
  FOR SELECT
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  );

-- LISTEN/NOTIFY: emit a per-tenant invalidation signal on every change.
CREATE OR REPLACE FUNCTION tenant_config_notify_fn() RETURNS TRIGGER AS $$
DECLARE
  tid TEXT;
BEGIN
  tid := COALESCE(NEW.tenant_id, OLD.tenant_id);
  PERFORM pg_notify('tenant_config_changed', tid);
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tenant_config_notify_trigger
  AFTER INSERT OR UPDATE OR DELETE ON tenant_config
  FOR EACH ROW EXECUTE FUNCTION tenant_config_notify_fn();

-- Atomic-audit trigger: every write produces a kind=tenant_config_change audit row in
-- the same transaction (FR-013b + SC-014). Mirrors the break-glass atomic-audit pattern.
CREATE OR REPLACE FUNCTION tenant_config_audit_fn() RETURNS TRIGGER AS $$
DECLARE
  event_id TEXT;
  prior_values JSONB;
  new_values JSONB;
  cid TEXT;
BEGIN
  event_id := encode(gen_random_bytes(16), 'hex');
  prior_values := CASE
    WHEN TG_OP IN ('UPDATE', 'DELETE') THEN
      jsonb_build_object(
        'inbound_sustained_rps', OLD.inbound_sustained_rps,
        'inbound_burst_capacity', OLD.inbound_burst_capacity,
        'query_sustained_rps', OLD.query_sustained_rps,
        'query_burst_capacity', OLD.query_burst_capacity
      )
    ELSE NULL
  END;
  new_values := CASE
    WHEN TG_OP IN ('INSERT', 'UPDATE') THEN
      jsonb_build_object(
        'inbound_sustained_rps', NEW.inbound_sustained_rps,
        'inbound_burst_capacity', NEW.inbound_burst_capacity,
        'query_sustained_rps', NEW.query_sustained_rps,
        'query_burst_capacity', NEW.query_burst_capacity
      )
    ELSE NULL
  END;
  cid := COALESCE(
    current_setting('app.correlation_id', true),
    'tenant-config-' || event_id
  );
  INSERT INTO audit_events (
    event_id, tenant_id, kind, originating_finding,
    principal_subject, correlation_id, occurred_at
  ) VALUES (
    event_id,
    COALESCE(NEW.tenant_id, OLD.tenant_id),
    'tenant_config_change',
    jsonb_build_object(
      'service_principal_subject', COALESCE(NEW.updated_by_subject, OLD.updated_by_subject),
      'target_tenant_id', COALESCE(NEW.tenant_id, OLD.tenant_id),
      'prior_values', prior_values,
      'new_values', new_values
    ),
    COALESCE(NEW.updated_by_subject, OLD.updated_by_subject),
    cid,
    now()
  );
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tenant_config_audit_trigger
  AFTER INSERT OR UPDATE OR DELETE ON tenant_config
  FOR EACH ROW EXECUTE FUNCTION tenant_config_audit_fn();
