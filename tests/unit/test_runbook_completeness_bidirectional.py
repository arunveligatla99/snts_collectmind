"""T283 red-phase test: bidirectional runbook-completeness contract (feature 002 Phase 13).

Phase 13 T283 extends ``scripts/check_runbook_completeness.py`` (feature-001 T113) to
enforce a BIDIRECTIONAL invariant:

    Forward (existing T113): every alert in ``rules.yaml`` MUST link to a runbook page
        that exists on disk under ``observability/runbooks/`` AND that runbook page
        MUST contain the four canonical sections (Symptoms / Dashboard / Mitigation /
        Escalation).
    Backward (NEW at T283): every Markdown runbook page under ``observability/runbooks/``
        MUST be referenced by at least one alert's ``runbook_url`` annotation OR be
        listed in an explicit operational-reference whitelist (operational failure
        modes documented without a Prometheus alert — e.g.
        ``docker-desktop-daemon-down.md``, ``slm-container-oom.md``,
        ``cpu-fallback-activation.md``, etc.).

This file pins the backward direction. Phase 13.b (T283) lands the implementation by
adding a ``find_orphan_runbooks(rules_doc, runbook_dir, whitelist)`` function to
``scripts/check_runbook_completeness.py`` and wiring it into the ``check()`` entry point
so the CI gate fails on either direction.

Red-phase signal: ``find_orphan_runbooks`` does not yet exist; the import below raises
``ImportError``. The synthetic-orphan test exercises the function once it lands.

Anchors: FR-024 / Principle V / Principle VII / Principle VIII / Principle IV.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = REPO_ROOT / "observability" / "prometheus" / "rules.yaml"
RUNBOOK_DIR = REPO_ROOT / "observability" / "runbooks"
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Ensure ``scripts/`` is importable so the script can be loaded as a module.
sys.path.insert(0, str(SCRIPTS_DIR))


def _try_import_find_orphan_runbooks():
    """Lazy import so the red-phase signal lands as a single skip-or-fail per test
    instead of a module-level collection error that obscures the missing function."""
    try:
        from check_runbook_completeness import find_orphan_runbooks  # type: ignore[attr-defined]
    except ImportError:
        return None
    return find_orphan_runbooks


def test_find_orphan_runbooks_function_exists() -> None:
    """Phase 13 T283 MUST add ``find_orphan_runbooks`` to the CI guard module.

    The function signature is the contract — a free function that takes a parsed
    ``rules.yaml`` doc, a runbook directory, and an optional whitelist set, and returns
    a list of orphan runbook filenames (relative to the runbook directory). Returning
    ``[]`` means the bidirectional invariant holds.
    """
    fn = _try_import_find_orphan_runbooks()
    assert fn is not None, (
        "Phase 13 T283 has not landed: ``find_orphan_runbooks`` missing from "
        "``scripts/check_runbook_completeness.py``. The bidirectional invariant requires "
        "this function so every runbook page is verified to be referenced by at least "
        "one alert (or whitelisted as an operational reference)."
    )


def test_find_orphan_runbooks_returns_empty_for_current_repo_state() -> None:
    """After Phase 13 T280 + T283 land, the current repo MUST have zero orphan runbooks.

    This is the bidirectional contract's enforcement against the live tree. Every
    runbook in ``observability/runbooks/`` MUST either be referenced by an alert or be
    in the documented operational-reference whitelist. Phase 12's
    ``deployment-tenant-mismatch.md`` becomes alert-referenced once T280 lands the
    ``DeploymentTenantMismatch`` rule; until then it's an orphan and this test fails.
    """
    fn = _try_import_find_orphan_runbooks()
    if fn is None:
        pytest.fail(
            "Phase 13 T283 has not landed: ``find_orphan_runbooks`` missing. The "
            "current-repo orphan check cannot run; this is the canonical red signal."
        )
    rules_doc = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or {}
    orphans = fn(rules_doc, RUNBOOK_DIR)
    assert orphans == [], (
        f"bidirectional invariant violated: {len(orphans)} orphan runbook(s) — each "
        f"file MUST be referenced by an alert or whitelisted. Orphans: {orphans}"
    )


def test_find_orphan_runbooks_flags_synthetic_orphan(tmp_path: Path) -> None:
    """Synthetic test: drop a runbook page into a private dir that no alert references,
    pass the dir to ``find_orphan_runbooks``, assert it's flagged.

    Together with ``test_find_orphan_runbooks_returns_empty_for_current_repo_state``,
    this proves both directions of the function: it correctly reports orphans AND
    correctly returns empty when none exist.
    """
    fn = _try_import_find_orphan_runbooks()
    if fn is None:
        pytest.fail("Phase 13 T283 has not landed.")
    synthetic_runbook = tmp_path / "orphan-with-no-alert.md"
    synthetic_runbook.write_text("# Orphan\n\n## Symptoms\n\nnone\n", encoding="utf-8")
    # An empty rules doc has no alerts referencing the file; it MUST be flagged.
    orphans = fn({"groups": []}, tmp_path)
    assert "orphan-with-no-alert.md" in orphans, (
        f"find_orphan_runbooks failed to flag a synthetic orphan; got {orphans}"
    )


def test_find_orphan_runbooks_respects_whitelist(tmp_path: Path) -> None:
    """Whitelist contract: operational-reference runbook pages (no alert by design) MUST
    be skipped when listed in the whitelist set passed by the caller.

    The script's CI-mode whitelist is the canonical list; the test exercises the
    parameter to prove the function honors it.
    """
    fn = _try_import_find_orphan_runbooks()
    if fn is None:
        pytest.fail("Phase 13 T283 has not landed.")
    synthetic_runbook = tmp_path / "operational-reference.md"
    synthetic_runbook.write_text("# Op-ref\n\n## Symptoms\n\nnone\n", encoding="utf-8")
    orphans = fn({"groups": []}, tmp_path, whitelist={"operational-reference.md"})
    assert "operational-reference.md" not in orphans, (
        f"find_orphan_runbooks did not honor the whitelist; got {orphans}"
    )
