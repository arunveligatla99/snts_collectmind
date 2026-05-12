"""T251: FR-012 default rate-limit values parity test.

Asserts the Phase 10.b ``src/collectmind/ratelimit/defaults.py`` module exports the FR-012
verbatim defaults:
    - Inbound endpoint: sustained 2000 r/s, burst 4000.
    - Query endpoints: sustained 200 r/s, burst 400.

Asserts the binding rate-limit-vs-SLO distinction (FR-012a) by name. The runbook page
``observability/runbooks/ratelimit-sustained-throttle.md`` (Phase 10.b T260) MUST warn
operators against lowering the inbound default to "match the SLO."

Red phase: Phase 10.b T257 (defaults.py) hasn't landed. Import fails.

Anchors: FR-012 / FR-012a / Principle IV.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DEFAULTS_PATH = Path(__file__).resolve().parents[2] / "src" / "collectmind" / "ratelimit" / "defaults.py"


def test_defaults_module_exists() -> None:
    """Red signal: file missing → Phase 10.b T257 pending."""
    assert DEFAULTS_PATH.exists(), (
        f"Phase 10.b T257 has not landed: {DEFAULTS_PATH} missing"
    )


def test_inbound_defaults_match_fr012() -> None:
    """Inbound: 2000 r/s sustained + burst 4000."""
    from collectmind.ratelimit import defaults

    assert defaults.DEFAULT_INBOUND_SUSTAINED_RPS == 2000, (
        f"FR-012 violation: inbound sustained should be 2000; got {defaults.DEFAULT_INBOUND_SUSTAINED_RPS}"
    )
    assert defaults.DEFAULT_INBOUND_BURST == 4000, (
        f"FR-012 violation: inbound burst should be 4000; got {defaults.DEFAULT_INBOUND_BURST}"
    )


def test_query_defaults_match_fr012() -> None:
    """Query: 200 r/s sustained + burst 400."""
    from collectmind.ratelimit import defaults

    assert defaults.DEFAULT_QUERY_SUSTAINED_RPS == 200, (
        f"FR-012 violation: query sustained should be 200; got {defaults.DEFAULT_QUERY_SUSTAINED_RPS}"
    )
    assert defaults.DEFAULT_QUERY_BURST == 400, (
        f"FR-012 violation: query burst should be 400; got {defaults.DEFAULT_QUERY_BURST}"
    )


def test_burst_capacity_is_2x_sustained() -> None:
    """ADR-0008 Part 1: 2x SLO sustained / 4x SLO burst pattern (2x of sustained = burst)."""
    from collectmind.ratelimit import defaults

    assert defaults.DEFAULT_INBOUND_BURST == defaults.DEFAULT_INBOUND_SUSTAINED_RPS * 2, (
        "ADR-0008 Part 1: inbound burst = 2x inbound sustained"
    )
    assert defaults.DEFAULT_QUERY_BURST == defaults.DEFAULT_QUERY_SUSTAINED_RPS * 2, (
        "ADR-0008 Part 1: query burst = 2x query sustained"
    )


def test_runbook_warns_against_matching_slo() -> None:
    """FR-012a contract: the runbook MUST warn operators against lowering the inbound
    default to "match the SLO." Phase 10.b T260 ships the runbook page; this test gates it.
    """
    runbook = (
        Path(__file__).resolve().parents[2]
        / "observability"
        / "runbooks"
        / "ratelimit-sustained-throttle.md"
    )
    if not runbook.exists():
        pytest.fail(
            f"Phase 10.b T260 has not landed: {runbook} missing. "
            f"FR-012a requires the rate-limit-vs-SLO distinction documented in the runbook."
        )
    content = runbook.read_text(encoding="utf-8").lower()
    assert "slo" in content, "runbook MUST reference the SLO for the rate-limit distinction"
    # The exact warning wording is implementation-detail; the test asserts the warning is
    # present in some form. A future operator reading the runbook MUST see the distinction.
    keywords = ["sc-002", "1000", "rate limit is not the slo", "structurally unattainable"]
    assert any(kw in content for kw in keywords), (
        f"FR-012a violation: runbook MUST warn against lowering the inbound default to "
        f"match the SLO; expected one of {keywords!r} in runbook text"
    )
