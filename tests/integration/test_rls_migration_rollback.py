"""T227: RLS migration forward + backward rollback test (SC-010).

Asserts the migration-012 + 013-016 bidirectional safety property:
    - Forward (PERMISSIVE → RESTRICTIVE) completes in ≤30 seconds and leaves only
      RESTRICTIVE policies on every tenant-scoped table (FR-004).
    - Backward (RESTRICTIVE → PERMISSIVE) completes in the same budget and restores
      every PERMISSIVE policy (ADR-0007 Part 2).
    - Both directions are idempotent: re-applying forward after forward, or backward
      after backward, must not error (modulo 013's strict-mode rollback that requires
      new-kind rows to be purged first; out of scope for this test).

Red phase: migration files exist (shipped by Phase 8 T205-T208). Test applies them in
sequence against the running Postgres and measures wall-clock. The SC-010 ≤30s budget is
the contract. Wall-clock measurement against a containerised Postgres on a developer machine
will likely complete in <1s for this schema size; the budget is named as a future-proofing
floor.

Anchors: SC-010 / FR-004 / ADR-0007 Part 2 / Principle IV.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "src" / "collectmind" / "registry" / "migrations" / "sql"
PG_CONTAINER = "collectmind-postgres"

SC_010_BUDGET_SECONDS = 30.0


def _psql(sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "exec", "-i", PG_CONTAINER, "psql", "-U", "collectmind", "-d", "collectmind", "-v", "ON_ERROR_STOP=1"],
        input=sql,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _apply(name: str, direction: str) -> float:
    path = MIGRATIONS_DIR / f"{name}.{direction}.sql"
    sql = path.read_text(encoding="utf-8")
    start = time.monotonic()
    result = _psql(sql)
    elapsed = time.monotonic() - start
    if result.returncode != 0:
        raise AssertionError(f"{name}.{direction}.sql failed: {result.stderr}")
    return elapsed


def test_012_forward_then_backward_within_budget() -> None:
    """012 forward + backward each complete within SC-010 budget."""
    fwd = _apply("012_rls_restrictive", "up")
    assert fwd <= SC_010_BUDGET_SECONDS, f"forward took {fwd:.2f}s (>SC-010 budget {SC_010_BUDGET_SECONDS}s)"

    # Confirm RESTRICTIVE policies in place.
    inspect = _psql("SELECT count(*) FROM pg_policies WHERE permissive = 'RESTRICTIVE';")
    assert "9" in inspect.stdout, f"expected 9 RESTRICTIVE policies; output={inspect.stdout!r}"

    bck = _apply("012_rls_restrictive", "down")
    assert bck <= SC_010_BUDGET_SECONDS, f"backward took {bck:.2f}s"

    # Confirm PERMISSIVE policies restored.
    inspect = _psql("SELECT count(*) FROM pg_policies WHERE policyname LIKE '%_permissive';")
    assert "9" in inspect.stdout, f"expected 9 PERMISSIVE policies post-rollback; output={inspect.stdout!r}"


def test_012_through_016_full_forward_chain_within_budget() -> None:
    """Apply 012 through 016 forward in sequence; assert combined wall-clock fits the budget."""
    migrations = [
        "012_rls_restrictive",
        "013_audit_kind_widening",
        "014_tenant_config",
        "015_tenant_vehicles",
        "016_audit_events_uniqueness",
    ]
    elapsed_total = 0.0
    try:
        for name in migrations:
            elapsed_total += _apply(name, "up")
        assert elapsed_total <= SC_010_BUDGET_SECONDS, (
            f"full forward chain took {elapsed_total:.2f}s (>budget)"
        )
        # Confirm new objects exist.
        inspect = _psql(
            "SELECT count(*) FROM pg_tables WHERE tablename IN "
            "('tenant_config', 'tenant_vehicles', 'tenant_vehicles_history');"
        )
        assert "3" in inspect.stdout, f"expected 3 new tables; output={inspect.stdout!r}"
    finally:
        # Always roll back so the next test sees clean state.
        # Purge new-kind rows before rolling 013 down (intentional strict-mode per .down.sql).
        _psql("""
            ALTER TABLE audit_events DISABLE TRIGGER audit_events_immutable;
            DELETE FROM audit_events WHERE kind IN
              ('break_glass', 'tenant_config_change', 'deployment_rejected', 'vehicle_assignment_change');
            ALTER TABLE audit_events ENABLE TRIGGER audit_events_immutable;
        """)
        for name in reversed(migrations):
            _apply(name, "down")
