"""OpenTelemetry init (§1.12) — a graceful no-op when no collector is configured."""

from __future__ import annotations

from kg_common.logging import get_logger

_log = get_logger(__name__)


def setup_observability(service_name: str) -> None:
    """Best-effort tracing init. Never raises if OTel is absent/misconfigured."""
    from kg_common.config import get_settings

    endpoint = get_settings().otel_endpoint
    if not endpoint:
        _log.debug("otel.disabled", service=service_name)
        return
    try:  # optional dependency — do not hard-require in embedded profile
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        _log.info("otel.enabled", service=service_name, endpoint=endpoint)
    except Exception as exc:  # telemetry must never break the app
        _log.warning("otel.init_failed", service=service_name, error=str(exc))
