from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


def setup_tracing(service_name: str = "orion-mcp-v2") -> None:
    """Inicializa OTEL com exporter de consola quando dependências existem; caso contrário no-op."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _logger.info("OpenTelemetry tracer inicializado (ConsoleSpanExporter)")
    except Exception:
        _logger.debug("OTEL não configurado", exc_info=True)
