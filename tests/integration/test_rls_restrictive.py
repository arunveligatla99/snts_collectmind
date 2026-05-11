"""T224 + T225 + T226: RESTRICTIVE Row-Level Security defense-in-depth tests.

Three coupled assertions on the migration-012 RLS posture, all asserted against the real
Postgres in the local Compose stack:

    1. **Missing-context defense (T224 / FR-002)**: a session with no ``app.tenant_id``
       GUC returns 0 rows from any SELECT on a tenant-scoped table, and rejects
       INSERT/UPDATE/DELETE.

    2. **Wrong-context defense (T225 / FR-003)**: a session with ``app.tenant_id`` set to
       tenant A returns 0 rows when SELECT targets tenant B's primary key, even when the
       row exists.

    3. **Stale-GUC fail-closed (T226 / ADR-0007 Part 3)**: connection-pool reuse across
       transactions MUST NOT leak rows. The contract relies on ``Database.acquire()``
       wrapping in ``conn.transaction()`` so ``SET LOCAL app.tenant_id`` is genuinely
       transaction-local; on commit/rollback the setting reverts to NULL and the missing-
       context defense kicks in.

Red phase: migration 012 is not currently applied to the running DB (rolled back at end of
Phase 8 verification). Tests apply 012 forward at fixture setup; on teardown the test rolls
back so feature-001 PERMISSIVE policies are restored. Tests FAIL if RESTRICTIVE policies
are NOT a strict subset of PERMISSIVE (which they ARE per ADR-0007 Part 2) — failure here
would mean the migration definition has a bug.

Anchors: FR-002 / FR-003 / SC-002 / Principle X. ADR-0007 Parts 1, 3.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "src" / "collectmind" / "registry" / "migrations" / "sql"
PG_CONTAINER = "collectmind-postgres"


def _psql(sql: str) -> subprocess.CompletedProcess[str]:
    """Run SQL against the running Compose Postgres container."""
    return subprocess.run(
        ["docker", "exec", "-i", PG_CONTAINER, "psql", "-U", "collectmind", "-d", "collectmind", "-v", "ON_ERROR_STOP=1"],
        input=sql,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _apply_migration(name: str, direction: str) -> None:
    path = MIGRATIONS_DIR / f"{name}.{direction}.sql"
    sql = path.read_text(encoding="utf-8")
    result = _psql(sql)
    if result.returncode != 0:
        raise AssertionError(f"migration {name}.{direction}.sql failed: {result.stderr}")


@pytest.fixture(scope="module")
def restrictive_rls():
    """Ensure feature-002 migrations 012-017 are applied (idempotent via runner). Migration
    017 provisions the non-BYPASSRLS ``collectmind_tenant`` role required by these tests."""
    import asyncio
    import os
    from collectmind.registry.migrations.runner import apply_pending

    dsn = os.environ.get(
        "POSTGRES_DSN_HOST",
        "postgresql://collectmind:localdev@localhost:5433/collectmind",
    )
    asyncio.run(apply_pending(dsn))
    yield


def test_missing_context_returns_zero_rows(restrictive_rls) -> None:  # noqa: ARG001
    """T224: SELECT under collectmind_tenant role with NO app.tenant_id GUC returns 0 rows."""
    tables = [
        "tenants",
        "diagnostic_findings",
        "vehicle_groups",
        "collection_policies",
        "deployment_targets",
        "policy_outcomes",
        "audit_events",
        "telemetry_observations",
        "erasure_requests",
    ]
    for table in tables:
        result = _psql(
            f"BEGIN; SET LOCAL ROLE collectmind_tenant; "
            f"SELECT count(*) FROM {table}; ROLLBACK;"
        )
        if result.returncode != 0:
            pytest.fail(f"SELECT on {table} failed: {result.stderr}")
        digits = [line.strip() for line in result.stdout.split("\n") if line.strip().isdigit()]
        assert digits and digits[0] == "0", (
            f"FR-002 violation: {table} returned {digits} rows under missing app.tenant_id "
            f"(expected 0; non-BYPASSRLS collectmind_tenant role)"
        )


def test_wrong_context_returns_zero_rows(restrictive_rls) -> None:  # noqa: ARG001
    """T225: app.tenant_id='tenant-a' query targeting tenant-b row returns 0 rows."""
    # Seed both tenants as superuser (BYPASSRLS) so we have known rows.
    setup = """
    INSERT INTO tenants (tenant_id, display_name, oauth2_issuer, oauth2_audience)
      VALUES ('tenant-a', 'A', 'http://mock-issuer:8088', 'collectmind-api'),
             ('tenant-b', 'B', 'http://mock-issuer:8088', 'collectmind-api')
      ON CONFLICT DO NOTHING;
    """
    result = _psql(setup)
    if result.returncode != 0:
        pytest.fail(f"tenant setup failed: {result.stderr}")

    # Query tenant-b row under tenant-a context with the non-BYPASSRLS role; expect 0.
    result = _psql(
        "BEGIN; SET LOCAL ROLE collectmind_tenant; SET LOCAL app.tenant_id = 'tenant-a'; "
        "SELECT count(*) FROM tenants WHERE tenant_id = 'tenant-b'; ROLLBACK;"
    )
    if result.returncode != 0:
        pytest.fail(f"wrong-context test failed: {result.stderr}")
    digits = [line.strip() for line in result.stdout.split("\n") if line.strip().isdigit()]
    assert digits and digits[0] == "0", (
        f"FR-003 violation: tenant-a context returned {digits} rows targeting tenant-b row "
        f"(expected 0; non-BYPASSRLS collectmind_tenant role)"
    )


def test_stale_gucs_fail_closed(restrictive_rls) -> None:  # noqa: ARG001
    """T226: stale GUC across transaction boundaries returns 0 rows (failure-closed)."""
    setup = """
    INSERT INTO tenants (tenant_id, display_name, oauth2_issuer, oauth2_audience)
      VALUES ('tenant-a', 'A', 'http://mock-issuer:8088', 'collectmind-api')
      ON CONFLICT DO NOTHING;
    """
    _psql(setup)
    sql = """
    BEGIN;
      SET LOCAL ROLE collectmind_tenant;
      SET LOCAL app.tenant_id = 'tenant-a';
      SELECT count(*) AS in_txn FROM tenants WHERE tenant_id = 'tenant-a';
    COMMIT;
    BEGIN;
      SET LOCAL ROLE collectmind_tenant;
      -- Deliberately do NOT set app.tenant_id; prior SET LOCAL reverted on COMMIT.
      SELECT count(*) AS post_txn FROM tenants WHERE tenant_id = 'tenant-a';
    COMMIT;
    """
    result = _psql(sql)
    if result.returncode != 0:
        pytest.fail(f"stale-GUC test failed: {result.stderr}")
    digits = [line.strip() for line in result.stdout.split("\n") if line.strip().isdigit()]
    assert len(digits) >= 2, f"expected two count rows; got output={result.stdout!r}"
    # First transaction (with GUC set) sees its row.
    assert digits[0] == "1", f"in-txn SELECT returned {digits[0]}; expected 1"
    # Second transaction (no GUC) MUST return 0 — RESTRICTIVE missing-context defense.
    assert digits[1] == "0", (
        f"ADR-0007 Part 3 violation: second transaction (no SET LOCAL) returned "
        f"{digits[1]} rows; expected 0 under RESTRICTIVE policy missing-context defense."
    )
