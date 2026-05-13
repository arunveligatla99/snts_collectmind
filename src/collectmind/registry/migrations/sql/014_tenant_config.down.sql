-- 014 rollback.
DROP TRIGGER IF EXISTS tenant_config_audit_trigger  ON tenant_config;
DROP TRIGGER IF EXISTS tenant_config_notify_trigger ON tenant_config;
DROP FUNCTION IF EXISTS tenant_config_audit_fn();
DROP FUNCTION IF EXISTS tenant_config_notify_fn();
DROP POLICY  IF EXISTS tenant_config_restrictive_select ON tenant_config;
DROP POLICY  IF EXISTS tenant_config_permissive_baseline ON tenant_config;
DROP TABLE   IF EXISTS tenant_config;
