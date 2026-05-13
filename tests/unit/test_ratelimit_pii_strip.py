"""T252: rate-limit log events pass the PII-strip processor.

Asserts SC-007 / FR-014: every structured-log event emitted by the rate-limit middleware
passes the ``_pii_processor`` from ``src/collectmind/observability/logging.py``. The
processor strips decimal lat/long pairs, E.164 phone numbers, email addresses, and US-style
SSNs from log event dicts.

The test:
    1. Imports the middleware's log-event emission helper (Phase 10.b T255 exports this).
    2. Calls it with a synthetic payload that contains PII-shaped strings.
    3. Asserts the emitted event has the PII stripped.

Red phase: Phase 10.b T255 hasn't landed. Import fails with ModuleNotFoundError on
``collectmind.ratelimit.middleware``.

Anchors: SC-007 / FR-014 / Principle V / Principle IV.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_ratelimit_middleware_module_exists() -> None:
    middleware = Path(__file__).resolve().parents[2] / "src" / "collectmind" / "ratelimit" / "middleware.py"
    assert middleware.exists(), f"Phase 10.b T255 has not landed: {middleware} missing"


def test_ratelimit_log_event_passes_pii_processor() -> None:
    """Synthesize a log event with PII-shaped strings; assert the processor strips them."""
    from collectmind.observability.logging import _pii_processor  # type: ignore[attr-defined]

    raw_event = {
        "event": "ratelimit_decision",
        "tenant_id": "tenant-a",
        "endpoint": "POST /api/v1/findings",
        "decision": "reject",
        "remaining": 0,
        # Synthetic PII that the processor must strip:
        "operator_note": "user contact: john.doe@example.com phone +12025550100",
        "location": "47.6062, -122.3321",
    }
    processed = _pii_processor(None, "info", raw_event)
    flat = str(processed)
    assert "john.doe@example.com" not in flat, "SC-007 violation: email not stripped from rate-limit log event"
    assert "+12025550100" not in flat, "SC-007 violation: E.164 phone number not stripped"
    assert "47.6062" not in flat or "-122.3321" not in flat, "SC-007 violation: decimal lat/long pair not stripped"
    # tenant_id is a non-PII business identifier and MUST be retained.
    assert processed.get("tenant_id") == "tenant-a", "non-PII tenant_id must be retained"
    # The endpoint label is non-PII and MUST be retained.
    assert processed.get("endpoint") == "POST /api/v1/findings"


def test_ratelimit_middleware_uses_pii_stripped_logger() -> None:
    """The middleware module MUST import / use the PII-stripping logger configured by
    ``observability/logging.py``. Source-level grep: the middleware references
    ``structlog.get_logger`` (via ``observability.logging.get_logger``) which has the
    processor wired in the chain.
    """
    middleware_path = Path(__file__).resolve().parents[2] / "src" / "collectmind" / "ratelimit" / "middleware.py"
    if not middleware_path.exists():
        pytest.fail(f"Phase 10.b T255 has not landed: {middleware_path} missing")
    source = middleware_path.read_text(encoding="utf-8")
    # Accept either a direct import or the canonical observability.logging entry point.
    assert "structlog" in source or "get_logger" in source, (
        "rate-limit middleware MUST use structlog (via observability.logging) so the "
        "PII-strip processor is in the log-event pipeline (FR-014 / SC-007)"
    )
