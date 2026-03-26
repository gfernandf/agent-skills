"""I5 — Auto-configure OpenTelemetry from environment variables.

Call ``configure()`` once at startup (before any spans are created).
When the OTel SDK packages are installed *and* the standard env vars
are present, this wires up the OTLP exporter automatically.

Recognised env vars (standard OTel):
    OTEL_EXPORTER_OTLP_ENDPOINT   — e.g. http://localhost:4317
    OTEL_SERVICE_NAME              — defaults to ``agent-skills``
    OTEL_RESOURCE_ATTRIBUTES       — extra resource attributes

If the SDK is absent or the endpoint is not set, this is a silent no-op.
"""

from __future__ import annotations

import logging
import os

_logger = logging.getLogger(__name__)
_configured = False


def configure() -> bool:
    """Auto-configure the OTel SDK from env vars.  Returns True on success."""
    global _configured
    if _configured:
        return True

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        _logger.debug("OTEL_EXPORTER_OTLP_ENDPOINT not set — skipping OTel auto-config")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
    except ImportError:
        _logger.debug("OTel SDK packages not installed — skipping auto-config")
        return False

    service_name = os.getenv("OTEL_SERVICE_NAME", "agent-skills")
    resource = Resource.create({"service.name": service_name})

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=endpoint, insecure=endpoint.startswith("http://")
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    _configured = True
    _logger.info("OTel auto-configured: endpoint=%s service=%s", endpoint, service_name)
    return True
