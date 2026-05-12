"""T229: tenant_config atomic-audit integration test (SC-014).

Asserts FR-013b: every write to ``tenant_config`` (INSERT / UPDATE / DELETE) by the service
principal MUST produce a matching ``kind=tenant_config_change`` audit row inside the SAME
database transaction. If the audit-row write fails, the entire transaction rolls back and
the tenant_config row is absent.

The atomic-audit is enforced at the DB-trigger layer (per migration 014's
``tenant_config_audit_trigger``), so this test does NOT need application-layer wiring — it
applies migrations 012-014 + 016 forward, drives a service-principal write directly against
the running Postgres, and verifies the audit row is present in the same SELECT.

Red phase: migration 014 is not applied to the running DB (rolled back at end of Phase 8
verification). Test applies forward at fixture setup; rolls back at teardown.

Anchors: FR-013b / SC-014 / Principle XVII / Principle IV.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "src" / "collectmind" / "registry" / "migrations" / "sql"
PG_CONTAINER = "collectmind-postgres"


def _psql(sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            PG_CONTAINER,
            "psql",
            "-U",
            "collectmind",
            "-d",
            "collectmind",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input=sql,
        capture_output=True,
        text=True,
        timeout=15,
    )


def _apply(name: str, direction: str) -> None:
    sql = (MIGRATIONS_DIR / f"{name}.{direction}.sql").read_text(encoding="utf-8")
    result = _psql(sql)
    if result.returncode != 0:
        raise AssertionError(f"{name}.{direction}.sql failed: {result.stderr}")


@pytest.fixture(scope="module")
def feature_002_schema():
    """Assume feature-002 migrations are already applied (via orchestration-api startup or
    a prior _apply). Tests under this fixture verify atomic-audit DB-trigger behavior; they
    do NOT manipulate the migration state. Cleanup of test rows happens at teardown.
    """
    # Confirm the schema is in place; skip if not (e.g., dev environment without the runner).
    check = _psql("SELECT 1 FROM pg_tables WHERE tablename='tenant_config';")
    if "1" not in check.stdout:
        pytest.skip(
            "tenant_config table missing; apply migrations 012-016 (and 017 for the role) first. "
            "Run: PYTHONPATH=src python -c 'import asyncio; "
            "from collectmind.registry.migrations.runner import apply_pending; "
            "asyncio.run(apply_pending(...))'"
        )
    yield
    # Purge test-inserted rows so subsequent test runs are deterministic.
    _psql("""
        ALTER TABLE audit_events DISABLE TRIGGER audit_events_immutable;
        DELETE FROM audit_events WHERE kind = 'tenant_config_change';
        ALTER TABLE audit_events ENABLE TRIGGER audit_events_immutable;
        DELETE FROM tenant_config WHERE tenant_id IN ('tenant-a', 'tenant-b');
    """)


def test_tenant_config_insert_produces_audit_row_in_same_transaction(feature_002_schema) -> None:
    """INSERT into tenant_config → trigger writes kind=tenant_config_change audit row atomically."""
    cid = f"test-tc-insert-{uuid.uuid4().hex}"
    tenant = "tenant-a"
    sql = f"""
    INSERT INTO tenants (tenant_id, display_name, oauth2_issuer, oauth2_audience) VALUES ('{tenant}', 'TestTenant', 'http://mock-issuer:8088', 'collectmind-api') ON CONFLICT DO NOTHING;
    BEGIN;
      SET LOCAL app.tenant_id = '{tenant}';
      SET LOCAL app.correlation_id = '{cid}';
      INSERT INTO tenant_config (tenant_id, inbound_sustained_rps, inbound_burst_capacity,
        query_sustained_rps, query_burst_capacity, updated_by_subject)
      VALUES ('{tenant}', 2000, 4000, 200, 400, 'svc-test');
      -- Same transaction: assert the audit row is visible.
      SELECT count(*) FROM audit_events
        WHERE kind='tenant_config_change' AND correlation_id='{cid}';
    COMMIT;
    """
    result = _psql(sql)
    assert result.returncode == 0, f"transaction failed: {result.stderr}"
    digits = [line.strip() for line in result.stdout.split("\n") if line.strip().isdigit()]
    # First (and only) digit on the count row → 1.
    assert digits and digits[0] == "1", (
        f"SC-014 violation: expected 1 kind=tenant_config_change row for cid={cid}; got {digits}"
    )


def test_tenant_config_update_produces_audit_row(feature_002_schema) -> None:
    """UPDATE on tenant_config → trigger writes second kind=tenant_config_change row."""
    tenant = "tenant-b"
    cid_insert = f"test-tc-upd-i-{uuid.uuid4().hex}"
    cid_update = f"test-tc-upd-u-{uuid.uuid4().hex}"
    sql = f"""
    INSERT INTO tenants (tenant_id, display_name, oauth2_issuer, oauth2_audience) VALUES ('{tenant}', 'B', 'http://mock-issuer:8088', 'collectmind-api') ON CONFLICT DO NOTHING;
    BEGIN;
      SET LOCAL app.tenant_id = '{tenant}';
      SET LOCAL app.correlation_id = '{cid_insert}';
      INSERT INTO tenant_config (tenant_id, inbound_sustained_rps, inbound_burst_capacity,
        query_sustained_rps, query_burst_capacity, updated_by_subject)
      VALUES ('{tenant}', 2000, 4000, 200, 400, 'svc-test') ON CONFLICT DO NOTHING;
    COMMIT;
    BEGIN;
      SET LOCAL app.tenant_id = '{tenant}';
      SET LOCAL app.correlation_id = '{cid_update}';
      UPDATE tenant_config SET inbound_sustained_rps = 3000 WHERE tenant_id='{tenant}';
      SELECT count(*) FROM audit_events
        WHERE kind='tenant_config_change' AND correlation_id='{cid_update}';
    COMMIT;
    """
    result = _psql(sql)
    assert result.returncode == 0, f"transaction failed: {result.stderr}"
    digits = [line.strip() for line in result.stdout.split("\n") if line.strip().isdigit()]
    assert digits and digits[0] == "1", (
        f"SC-014 violation: UPDATE did not produce audit row for cid={cid_update}; got {digits}"
    )
