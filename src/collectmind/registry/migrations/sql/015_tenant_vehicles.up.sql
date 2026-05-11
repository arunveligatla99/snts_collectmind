-- 015: tenant_vehicles current ownership + tenant_vehicles_history append-only log.
-- Feature 002 / ADR-0009 / FR-021 / FR-023.

-- Current-state table (one row per vehicle). Mutable tenant_id; history trigger captures every change.
CREATE TABLE IF NOT EXISTS tenant_vehicles (
  vehicle_id          TEXT PRIMARY KEY CHECK (vehicle_id <> ''),
  tenant_id           TEXT NOT NULL REFERENCES tenants(tenant_id),
  assigned_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  assigned_by_subject TEXT NOT NULL CHECK (assigned_by_subject <> ''),
  reason_code         TEXT NOT NULL CHECK (reason_code IN (
    'initial_provisioning', 'resale', 'fleet_reassignment',
    'oem_handoff', 'lease_return', 'totaled', 'other'
  ))
);

ALTER TABLE tenant_vehicles ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_vehicles_restrictive ON tenant_vehicles AS RESTRICTIVE
  FOR SELECT
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND tenant_id = current_setting('app.tenant_id', true)
  );

-- Append-only history (rows insert-only; UPDATE/DELETE blocked by trigger).
CREATE TABLE IF NOT EXISTS tenant_vehicles_history (
  history_id        BIGSERIAL PRIMARY KEY,
  vehicle_id        TEXT NOT NULL,
  prev_tenant_id    TEXT,
  new_tenant_id     TEXT NOT NULL,
  operator_subject  TEXT NOT NULL CHECK (operator_subject <> ''),
  reason_code       TEXT NOT NULL CHECK (reason_code IN (
    'initial_provisioning', 'resale', 'fleet_reassignment',
    'oem_handoff', 'lease_return', 'totaled', 'other'
  )),
  transition_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  correlation_id    TEXT NOT NULL CHECK (correlation_id <> '')
);

CREATE INDEX IF NOT EXISTS tenant_vehicles_history_vehicle_idx ON tenant_vehicles_history (vehicle_id, transition_at);
CREATE INDEX IF NOT EXISTS tenant_vehicles_history_prev_idx    ON tenant_vehicles_history (prev_tenant_id, transition_at);
CREATE INDEX IF NOT EXISTS tenant_vehicles_history_new_idx     ON tenant_vehicles_history (new_tenant_id, transition_at);

ALTER TABLE tenant_vehicles_history ENABLE ROW LEVEL SECURITY;

-- Tenant sees rows where they were either the prior or new owner.
CREATE POLICY tenant_vehicles_history_restrictive ON tenant_vehicles_history AS RESTRICTIVE
  FOR SELECT
  USING (
    current_setting('app.tenant_id', true) IS NOT NULL
    AND (
      prev_tenant_id = current_setting('app.tenant_id', true)
      OR new_tenant_id = current_setting('app.tenant_id', true)
    )
  );

-- Immutability trigger.
CREATE OR REPLACE FUNCTION tenant_vehicles_history_immutable_fn() RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'tenant_vehicles_history is append-only; UPDATE and DELETE not permitted';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tenant_vehicles_history_immutable
  BEFORE UPDATE OR DELETE ON tenant_vehicles_history
  FOR EACH ROW EXECUTE FUNCTION tenant_vehicles_history_immutable_fn();

-- History append trigger fires on every INSERT (initial) or UPDATE OF tenant_id (transfer).
CREATE OR REPLACE FUNCTION tenant_vehicles_history_fn() RETURNS TRIGGER AS $$
DECLARE
  prev_tid TEXT;
  cid TEXT;
BEGIN
  IF TG_OP = 'INSERT' THEN
    prev_tid := NULL;
  ELSE
    prev_tid := OLD.tenant_id;
    IF prev_tid IS NOT DISTINCT FROM NEW.tenant_id THEN
      RETURN NEW;
    END IF;
  END IF;
  cid := COALESCE(
    current_setting('app.correlation_id', true),
    'vehicle-' || NEW.vehicle_id || '-' || encode(gen_random_bytes(6), 'hex')
  );
  INSERT INTO tenant_vehicles_history (
    vehicle_id, prev_tenant_id, new_tenant_id, operator_subject, reason_code, transition_at, correlation_id
  ) VALUES (
    NEW.vehicle_id, prev_tid, NEW.tenant_id, NEW.assigned_by_subject, NEW.reason_code, NEW.assigned_at, cid
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tenant_vehicles_history_trigger
  AFTER INSERT OR UPDATE OF tenant_id ON tenant_vehicles
  FOR EACH ROW EXECUTE FUNCTION tenant_vehicles_history_fn();

-- Atomic-audit trigger: every assignment produces a kind=vehicle_assignment_change row.
CREATE OR REPLACE FUNCTION tenant_vehicles_audit_fn() RETURNS TRIGGER AS $$
DECLARE
  event_id TEXT;
  prior_tid TEXT;
  cid TEXT;
BEGIN
  event_id := encode(gen_random_bytes(16), 'hex');
  IF TG_OP = 'INSERT' THEN
    prior_tid := NULL;
  ELSE
    prior_tid := OLD.tenant_id;
    IF prior_tid IS NOT DISTINCT FROM NEW.tenant_id THEN
      RETURN NEW;
    END IF;
  END IF;
  cid := COALESCE(
    current_setting('app.correlation_id', true),
    'vehicle-assignment-' || event_id
  );
  INSERT INTO audit_events (
    event_id, tenant_id, kind, originating_finding,
    principal_subject, correlation_id, occurred_at
  ) VALUES (
    event_id,
    NEW.tenant_id,
    'vehicle_assignment_change',
    jsonb_build_object(
      'service_principal_subject', NEW.assigned_by_subject,
      'vehicle_id', NEW.vehicle_id,
      'prior_tenant_id', prior_tid,
      'new_tenant_id', NEW.tenant_id,
      'reason_code', NEW.reason_code
    ),
    NEW.assigned_by_subject,
    cid,
    now()
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tenant_vehicles_audit_trigger
  AFTER INSERT OR UPDATE OF tenant_id ON tenant_vehicles
  FOR EACH ROW EXECUTE FUNCTION tenant_vehicles_audit_fn();
