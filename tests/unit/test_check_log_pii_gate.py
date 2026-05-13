"""T290 red-phase test: PII-strip CI gate (closes feature-001 SC-007 + feature-002 SC-007).

Pins three contracts that the Phase 14 T290 CI gate at ``scripts/check_log_pii.py``
MUST satisfy:

    1. The ``_pii_processor`` from ``src/collectmind/observability/logging.py`` MUST
       redact every PII pattern enumerated in the script's positive-case fixture
       (email, E.164 phone, decimal lat/long, US SSN, VIN). A regression in the
       processor (a pattern removed, a regex weakened) makes the CI gate fire.
    2. The processor MUST NOT redact non-PII business identifiers (tenant_id,
       correlation_id, policy_id, vehicle_id-as-business-key) — these are operational
       labels that downstream observability needs intact.
    3. The script's ``check()`` returns an empty list against the in-repo logging
       module + the declared metric labels; a non-empty list means CI fails.

Made green by ``scripts/check_log_pii.py`` + the script wired into
``.github/workflows/ci.yaml``'s ``custom-guards`` job (Phase 14 T290).

Red-phase signal: the script does not yet exist; the import below fails with
``ImportError``. The test is collection-stable because the import is lazy.

Anchors: SC-007 (feature 001 + feature 002) / FR-009 / Principle V / Principle IX /
Principle IV.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))


def _try_import_check() -> object | None:
    try:
        from check_log_pii import check  # type: ignore[attr-defined]
    except ImportError:
        return None
    return check


def _try_import_pii_processor() -> object | None:
    """Helper for negative-case assertions: the script MUST exercise the real processor."""
    from collectmind.observability.logging import _pii_processor

    return _pii_processor


def test_check_log_pii_script_exists() -> None:
    """Phase 14 T290 MUST add ``check_log_pii.py`` under ``scripts/``."""
    fn = _try_import_check()
    assert fn is not None, (
        "Phase 14 T290 has not landed: ``scripts/check_log_pii.py`` missing. Closes "
        "feature-001 SC-007 + feature-002 SC-007. Wire into "
        "``.github/workflows/ci.yaml``'s ``custom-guards`` job after the script lands."
    )


def test_check_log_pii_returns_empty_for_current_repo_state() -> None:
    """After T290 lands, the CI gate MUST report no PII regressions against the live
    ``_pii_processor`` + the declared metric labels."""
    fn = _try_import_check()
    if fn is None:
        pytest.fail("Phase 14 T290 has not landed: ``check_log_pii.check`` missing.")
    errors = fn()  # type: ignore[operator]
    assert errors == [], "PII-strip CI gate reported regressions:\n  - " + "\n  - ".join(errors)


@pytest.mark.parametrize(
    "synthetic_value, leak_token",
    [
        ("contact: user@example.com", "user@example.com"),
        ("phone: +12025550100", "+12025550100"),
        ("location 47.6062, -122.3321 fetched", "47.6062"),
        ("ssn 123-45-6789", "123-45-6789"),
    ],
)
def test_pii_processor_redacts_canonical_patterns(synthetic_value: str, leak_token: str) -> None:
    """Each canonical PII pattern in the processor MUST be redacted.

    Pins the per-pattern contract independent of the CI script — a regression in any
    one pattern would let synthetic PII through the processor and the script's
    ``check_pii_processor_strips_known_patterns`` would return a non-empty list, but
    this test localizes the failure to the pattern that regressed.
    """
    pii_processor = _try_import_pii_processor()
    assert pii_processor is not None
    event = {"event": "synthetic", "value": synthetic_value}
    processed = pii_processor(None, "info", event)  # type: ignore[operator]
    assert leak_token not in str(processed), (
        f"SC-007 violation: PII token {leak_token!r} not redacted by _pii_processor "
        f"(input was {synthetic_value!r}; output was {processed!r})"
    )


def test_pii_processor_preserves_non_pii_business_identifiers() -> None:
    """Non-PII identifiers (tenant_id, correlation_id, policy_id) MUST NOT be redacted.

    The processor's job is PII stripping, not opaque-token redaction. Business
    identifiers — even when they look superficially like opaque tokens — are
    operational labels that observability needs intact. A regression that redacts
    these would silently break the structured-log surface.
    """
    pii_processor = _try_import_pii_processor()
    assert pii_processor is not None
    event = {
        "event": "policy_generated",
        "tenant_id": "tenant-a",
        "correlation_id": "cid-abc-123",
        "policy_id": "policy-2026-05-11-001",
        "vehicle_id": "VIN-1HGCM82633A123456",
        "endpoint": "POST /api/v1/findings",
    }
    processed = pii_processor(None, "info", event)  # type: ignore[operator]
    assert processed["tenant_id"] == "tenant-a"
    assert processed["correlation_id"] == "cid-abc-123"
    assert processed["policy_id"] == "policy-2026-05-11-001"
    assert processed["vehicle_id"] == "VIN-1HGCM82633A123456"
    assert processed["endpoint"] == "POST /api/v1/findings"
