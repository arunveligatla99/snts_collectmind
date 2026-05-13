"""Unit tests for observability/otel.py (T134).

Targets the init path without actually starting an exporter pipeline; the
function should remain idempotent and not raise when called multiple times
in a single process.
"""

from __future__ import annotations

import importlib

from collectmind.observability import otel


def test_init_otel_does_not_raise_with_default_args() -> None:
    # Reload to reset any module-level state from earlier test ordering.
    importlib.reload(otel)
    otel.init_otel(service_name="test-service", otlp_endpoint="http://localhost:4317")


def test_init_otel_idempotent_on_second_call() -> None:
    otel.init_otel(service_name="test-service", otlp_endpoint="http://localhost:4317")
    otel.init_otel(service_name="test-service", otlp_endpoint="http://localhost:4317")


def test_init_otel_tolerates_missing_endpoint() -> None:
    importlib.reload(otel)
    # Missing endpoint MUST not raise; the exporter falls back to default
    # collector discovery semantics handled by the OTel SDK.
    otel.init_otel(service_name="svc", otlp_endpoint="")
