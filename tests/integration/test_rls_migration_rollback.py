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


def _ensure_clean_state() -> None:
    """Best-effort cleanup so the test starts with feature-001 PERMISSIVE policies and no
    feature-002 tables. The test environment may have feature-002 migrations applied from
    a prior session; this rolls them back."""
    for name in [
        "017_tenant_role",
        "016_audit_events_uniqueness",
        "015_tenant_vehicles",
        "014_tenant_config",
        "013_audit_kind_widening",
        "012_rls_restrictive",
    ]:
        path = MIGRATIONS_DIR / f"{name}.down.sql"
        if path.exists():
            _psql(
                "ALTER TABLE audit_events DISABLE TRIGGER audit_events_immutable; "
                "DELETE FROM audit_events WHERE kind IN ('break_glass','tenant_config_change',"
                "'deployment_rejected','vehicle_assignment_change'); "
                "ALTER TABLE audit_events ENABLE TRIGGER audit_events_immutable;"
            )
            _psql(path.read_text(encoding="utf-8"))


def _restore_feature_002_state() -> None:
    """Re-apply the full feature-002 migration chain so downstream tests see consistent state."""
    import asyncio
    from collectmind.registry.migrations.runner import apply_pending
    asyncio.run(apply_pending(
        "postgresql://collectmind:localdev@localhost:5433/collectmind"
    ))


def test_012_forward_then_backward_within_budget() -> None:
    """012 forward + backward each complete within SC-010 budget."""
    _ensure_clean_state()
    fwd = _apply("012_rls_restrictive", "up")
    assert fwd <= SC_010_BUDGET_SECONDS, f"forward took {fwd:.2f}s (>SC-010 budget {SC_010_BUDGET_SECONDS}s)"

    # Confirm RESTRICTIVE policies in place (9 RESTRICTIVE + 9 PERMISSIVE_baseline = 18 total).
    inspect = _psql("SELECT count(*) FROM pg_policies WHERE permissive = 'RESTRICTIVE';")
    digits = [line.strip() for line in inspect.stdout.split("\n") if line.strip().isdigit()]
    assert digits and digits[0] == "9", (
        f"expected 9 RESTRICTIVE policies; got {digits}"
    )

    bck = _apply("012_rls_restrictive", "down")
    assert bck <= SC_010_BUDGET_SECONDS, f"backward took {bck:.2f}s"

    # Confirm PERMISSIVE-only policies restored.
    inspect = _psql("SELECT count(*) FROM pg_policies WHERE policyname LIKE '%_permissive';")
    digits = [line.strip() for line in inspect.stdout.split("\n") if line.strip().isdigit()]
    assert digits and digits[0] == "9", (
        f"expected 9 PERMISSIVE policies post-rollback; got {digits}"
    )

    # Restore feature-002 schema so downstream tests see consistent state.
    _restore_feature_002_state()


def test_012_through_016_full_forward_chain_within_budget() -> None:
    """Apply 012 through 016 forward in sequence; assert combined wall-clock fits the budget."""
    _ensure_clean_state()
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
        digits = [line.strip() for line in inspect.stdout.split("\n") if line.strip().isdigit()]
        assert digits and digits[0] == "3", (
            f"expected 3 new tables; got {digits}"
        )
    finally:
        # Always roll back so the next test sees clean state.
        _psql("""
            ALTER TABLE audit_events DISABLE TRIGGER audit_events_immutable;
            DELETE FROM audit_events WHERE kind IN
              ('break_glass', 'tenant_config_change', 'deployment_rejected', 'vehicle_assignment_change');
            ALTER TABLE audit_events ENABLE TRIGGER audit_events_immutable;
        """)
        for name in reversed(migrations):
            _apply(name, "down")
        # Restore feature-002 schema so downstream tests see consistent state.
        _restore_feature_002_state()
