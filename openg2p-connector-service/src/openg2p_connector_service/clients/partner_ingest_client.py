"""HTTP client for the registry partner ``POST /partner/ingest_data`` endpoint.

The registry ``G2PIngestController`` accepts the raw body as-is (via
``request.json()``). The optional ``data_model`` query parameter lets us
hint which DataModel to use if the payload signature is ambiguous.
"""

import logging
import time
from typing import Any

import httpx

from .. import metrics as connector_metrics
from ..config import get_settings

_logger = logging.getLogger("connector.client.partner_ingest")


def _status_class(code: int) -> str:
    return f"{code // 100}xx"


class PartnerIngestClient:
    async def send(
        self,
        payload: dict[str, Any],
        data_model: str | None = None,
        connector_id: str | None = None,
    ) -> str:
        """Post *payload* to the registry ingest endpoint.

        Returns the ``correlation_id`` from the registry response.
        """
        settings = get_settings()
        url = f"{settings.partner_ingest_base_url.rstrip('/')}/partner/ingest_data"
        params: dict[str, str] = {}
        if data_model:
            # Registry partner API uppercases the mnemonic before DB lookup.
            params["data_model"] = data_model.strip().upper()

        t0 = time.perf_counter()
        status_label = "error"
        try:
            async with httpx.AsyncClient(timeout=settings.partner_ingest_timeout) as client:
                _logger.info("POST %s data_model=%s", url, data_model)
                resp = await client.post(url, json=payload, params=params)
                status_label = _status_class(resp.status_code)
                resp.raise_for_status()
                body = resp.json()
        finally:
            connector_metrics.partner_duration.labels(
                connector_id=connector_id or "unknown",
            ).observe(time.perf_counter() - t0)
            connector_metrics.partner_requests_total.labels(
                connector_id=connector_id or "unknown",
                status_class=status_label,
            ).inc()

        # The Partner API always returns HTTP 200 — even on internal errors.
        # Detect application-level failures via the G2P response envelope and
        # raise so the connector treats them as failures (→ DLQ) rather than
        # silently logging them as success with an empty correlation_id.
        response_header = body.get("response_header") or {}
        if response_header.get("response_status") == "ERROR":
            err_code = response_header.get("response_error_code", "")
            err_msg = response_header.get("response_error_message", "unknown")
            raise ValueError(
                f"Partner API rejected payload: [{err_code}] {err_msg}"
            )

        # Keys may be present with JSON null — dict.get("k", {}) returns None if k maps to null.
        response_body = body.get("response_body") or {}
        response_payload = response_body.get("response_payload") or {}
        correlation_id = (
            response_payload.get("correlation_id")
            or body.get("correlation_id", "")
            or ""
        )
        _logger.info("Registry accepted payload, correlation_id=%s", correlation_id)
        return correlation_id
