"""Unit tests for observability/logging.py (T134).

Asserts the configure_logging factory wires structlog without raising and
that get_logger returns a structlog logger that accepts the FR-013 fields
(trace_id, tenant_id, correlation_id, schema_version) without error.
"""

from __future__ import annotations

import importlib

from collectmind.observability import logging as cm_logging


def test_configure_logging_does_not_raise() -> None:
    importlib.reload(cm_logging)
    cm_logging.configure_logging("INFO")
    cm_logging.configure_logging("DEBUG")


def test_get_logger_returns_bind_capable_logger() -> None:
    cm_logging.configure_logging("INFO")
    logger = cm_logging.get_logger("test.module")
    # structlog loggers accept .info(...) with arbitrary kwargs.
    logger.info("event_emitted", tenant_id="t", correlation_id="c", schema_version="1.0.0")
