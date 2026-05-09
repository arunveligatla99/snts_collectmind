"""Structured JSON logging with PII-stripping (FR-013, FR-017, SC-007)."""

from __future__ import annotations

import logging
import re
from typing import Any

import structlog

# Patterns we strip from any logged string. Conservative; the contract test in T142
# exercises each pattern. Adding patterns is cheap; removing one requires an ADR.
_PII_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Decimal lat/long pairs (precise geolocation).
    re.compile(r"-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}"),
    # E.164 phone numbers.
    re.compile(r"\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}"),
    # Email addresses.
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    # US-style SSN (defense-in-depth; not expected in this domain but cheap to strip).
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
)

_REDACTED = "[redacted]"


def _strip_pii(value: Any) -> Any:
    if isinstance(value, str):
        for pat in _PII_PATTERNS:
            value = pat.sub(_REDACTED, value)
    return value


def _pii_processor(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor that strips PII patterns from every string value."""
    for k, v in list(event_dict.items()):
        if isinstance(v, str):
            event_dict[k] = _strip_pii(v)
        elif isinstance(v, dict):
            event_dict[k] = {ik: _strip_pii(iv) for ik, iv in v.items()}
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib logging for JSON output with PII stripping."""
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _pii_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO),
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
