"""OpenTelemetry SDK initialization (Principle V)."""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


_initialized = False


def init_otel(service_name: str, otlp_endpoint: str) -> None:
    """Initialize the OTel tracer provider and OTLP exporter once per process."""
    global _initialized
    if _initialized:
        return
    if not otlp_endpoint or os.environ.get("DISABLE_OTEL", "").lower() in {"1", "true", "yes"}:
        _initialized = True
        return
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    _initialized = True


def tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
