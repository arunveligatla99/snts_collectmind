-- 015 rollback.
DROP TRIGGER IF EXISTS tenant_vehicles_audit_trigger    ON tenant_vehicles;
DROP TRIGGER IF EXISTS tenant_vehicles_history_trigger  ON tenant_vehicles;
DROP TRIGGER IF EXISTS tenant_vehicles_history_immutable ON tenant_vehicles_history;
DROP FUNCTION IF EXISTS tenant_vehicles_audit_fn();
DROP FUNCTION IF EXISTS tenant_vehicles_history_fn();
DROP FUNCTION IF EXISTS tenant_vehicles_history_immutable_fn();
DROP POLICY  IF EXISTS tenant_vehicles_history_restrictive ON tenant_vehicles_history;
DROP POLICY  IF EXISTS tenant_vehicles_restrictive         ON tenant_vehicles;
DROP TABLE   IF EXISTS tenant_vehicles_history;
DROP TABLE   IF EXISTS tenant_vehicles;
