#!/usr/bin/env python3
"""T290 — CI guard: structured log output + metric labels MUST not leak PII.

Closes feature-001 SC-007 + feature-002 SC-007. The gate enforces two properties:

  1. The ``_pii_processor`` in ``src/collectmind/observability/logging.py`` redacts
     every canonical PII pattern (email, E.164 phone, decimal lat/long pair, US SSN).
     A regression that weakens or removes a pattern fails this gate. Positive case:
     a PII-bearing event MUST come out redacted. Negative case (no-op preservation):
     a clean event with business identifiers (tenant_id, correlation_id, policy_id,
     vehicle_id) MUST pass through unchanged.

  2. Declared metric labels (across ``collectmind.observability.metrics`` and
     ``collectmind.ratelimit.metrics``) MUST NOT include label names that suggest
     PII carriers — ``email``, ``phone``, ``ssn``, ``personal_*``. These would route
     PII into the metric label cardinality regardless of how the value is sanitized
     at emission time.

VIN-shaped vehicle identifiers are business keys (the canonical primary key for the
vehicle within the tenant scope), NOT PII. The processor explicitly preserves them;
the CI gate does NOT flag VIN-shaped strings as a leak. If a future feature changes
this position, amend the processor + this gate via ADR.

Exit code 0 on success; non-zero with a printed error list on failure.

Wired into ``.github/workflows/ci.yaml``'s ``custom-guards`` job. Also runnable locally:

    python scripts/check_log_pii.py

The script mirrors ``tests/unit/test_check_log_pii_gate.py`` so a developer sees the
same failure surface in pytest and in CI.
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

# Canonical PII-bearing payloads. The processor MUST redact each leak token from each
# input string; if it doesn't, the matching pattern in
# ``observability/logging.py:_PII_PATTERNS`` has regressed.
_PII_FIXTURES: tuple[tuple[str, str], ...] = (
    ("contact: support@example.com please respond", "support@example.com"),
    ("call us at +1 202 555 0100 today", "+1 202 555 0100"),
    ("coords 47.6062, -122.3321 captured", "47.6062"),
    ("ssn 123-45-6789 on file", "123-45-6789"),
)

# Canonical non-PII business identifiers. The processor MUST pass these through
# unchanged; a regression that strips them would break the structured-log surface.
_PRESERVE_FIXTURES: dict[str, str] = {
    "tenant_id": "tenant-a",
    "correlation_id": "cid-abc-123",
    "policy_id": "policy-2026-05-11-001",
    "vehicle_id": "VIN-1HGCM82633A123456",
    "endpoint": "POST /api/v1/findings",
}

# Label name fragments that suggest a PII carrier. Metric label names MUST NOT match
# these (case-insensitive substring). Adding entries is cheap; removing entries
# requires an ADR (the constitution's Principle V says PII MUST NOT enter the
# observability surface).
_PII_LABEL_FRAGMENTS: tuple[str, ...] = (
    "email",
    "phone",
    "ssn",
    "personal_",
    "address",
    "geolocation",
)

# Metrics modules to scan. Add a module here when introducing a new metrics module.
_METRICS_MODULE_PATHS: tuple[str, ...] = (
    "collectmind.observability.metrics",
    "collectmind.ratelimit.metrics",
)


def check_pii_processor_strips_known_patterns() -> list[str]:
    """Run each PII fixture through the processor; flag any leak token that survives."""
    from collectmind.observability.logging import _pii_processor

    errors: list[str] = []
    for input_str, leak_token in _PII_FIXTURES:
        event = {"event": "synthetic", "value": input_str}
        processed = _pii_processor(None, "info", event)
        if leak_token in str(processed):
            errors.append(
                f"PII pattern regression: leak token {leak_token!r} survived "
                f"_pii_processor (input {input_str!r}; output {processed!r})"
            )
    return errors


def check_pii_processor_preserves_non_pii() -> list[str]:
    """Run a single event with non-PII business identifiers; flag any redaction."""
    from collectmind.observability.logging import _pii_processor

    event: dict[str, Any] = {"event": "policy_generated", **_PRESERVE_FIXTURES}
    processed = _pii_processor(None, "info", event)
    errors: list[str] = []
    for key, expected in _PRESERVE_FIXTURES.items():
        actual = processed.get(key)
        if actual != expected:
            errors.append(
                f"non-PII redaction regression: {key}={expected!r} became {actual!r} "
                f"after _pii_processor — the processor is over-stripping business identifiers"
            )
    return errors


def check_metric_label_names_bounded() -> list[str]:
    """Scan declared metric label names; flag any that match a PII fragment."""
    errors: list[str] = []
    for module_path in _METRICS_MODULE_PATHS:
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            continue
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            prom_name = getattr(attr, "_name", None)
            if not isinstance(prom_name, str) or not prom_name.startswith("collectmind_"):
                continue
            label_names = getattr(attr, "_labelnames", ())
            for label in label_names:
                lower = str(label).lower()
                for fragment in _PII_LABEL_FRAGMENTS:
                    if fragment in lower:
                        errors.append(
                            f"PII-labelled metric: {prom_name} carries label "
                            f"{label!r}; matches PII fragment {fragment!r}. Metric "
                            f"labels MUST NOT route PII into the cardinality "
                            f"(Principle V / FR-009)."
                        )
    return errors


def check() -> list[str]:
    """Run all three sub-checks; return the merged error list."""
    return (
        check_pii_processor_strips_known_patterns()
        + check_pii_processor_preserves_non_pii()
        + check_metric_label_names_bounded()
    )


def main(argv: list[str] | None = None) -> int:
    errors = check()
    if errors:
        print("PII-strip CI gate FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("PII-strip CI gate PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
