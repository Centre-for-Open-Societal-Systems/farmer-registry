"""Optional OpenTelemetry instrumentation.

Activated only when ``CONNECTOR_OTEL_ENABLED=true`` and the
``opentelemetry-*`` packages are installed.  Otherwise, a no-op.
"""

import logging

from fastapi import FastAPI

from .config import get_settings

_logger = logging.getLogger("connector.observability")


def instrument_app(app: FastAPI) -> None:
    settings = get_settings()
    if not settings.otel_enabled:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        _logger.info("OpenTelemetry FastAPI instrumentation enabled")
    except ImportError:
        _logger.debug(
            "CONNECTOR_OTEL_ENABLED is true but opentelemetry packages are not "
            "installed; skipping instrumentation"
        )
