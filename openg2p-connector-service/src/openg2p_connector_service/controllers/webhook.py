"""Webhook endpoints: POST /webhook/{connector_id} and /webhook/by-slug/{slug}.

Signature verification is delegated to pluggable verifiers.  When the
``process_webhook_task`` Celery task is available, the handler ACKs with
202 and enqueues heavy processing; otherwise it processes inline.
"""

import json
import logging
import uuid

import jmespath
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from ..config import get_settings
from ..database import get_session_factory
from ..models import ConnectorDefinition
from ..services import IngestionService
from ..webhooks.verifiers import verify_webhook

router = APIRouter(prefix="/webhook", tags=["webhook"])
_logger = logging.getLogger("connector.controller.webhook")
_ingestion = IngestionService()


async def _resolve_connector(
    identifier: str, *, by_slug: bool = False
) -> ConnectorDefinition:
    async with get_session_factory()() as session:
        if by_slug:
            result = await session.execute(
                select(ConnectorDefinition).where(
                    ConnectorDefinition.webhook_path_slug == identifier
                )
            )
            connector = result.scalar_one_or_none()
        else:
            connector = await session.get(ConnectorDefinition, identifier)

        if connector is None or not connector.is_active:
            raise HTTPException(404, "Connector not found or disabled")
        return connector


def _extract_payload(
    body_json: dict, connector: ConnectorDefinition
) -> tuple[str | None, dict]:
    """Return (source_event_id, data) after optional envelope extraction."""
    cfg = connector.get_source_config()
    data_path = cfg.get("webhook_payload_envelope", cfg.get("data_path"))

    if data_path:
        data = jmespath.search(data_path, body_json)
    else:
        data = body_json.get("data", body_json)

    if not isinstance(data, dict):
        raise HTTPException(400, "Extracted webhook data must be a dict")

    source_event_id = body_json.get("source_event_id")
    return source_event_id, data


async def _handle_webhook(connector_id: str, request: Request, *, by_slug: bool = False):
    raw_body = await request.body()

    try:
        body_json = json.loads(raw_body)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(400, f"Invalid JSON body: {exc}") from exc

    connector = await _resolve_connector(connector_id, by_slug=by_slug)
    secret = connector.webhook_secret or get_settings().webhook_default_secret
    verify_webhook(connector.webhook_verifier, secret, raw_body, dict(request.headers))

    source_event_id, data = _extract_payload(body_json, connector)

    if not source_event_id and isinstance(data, dict):
        source_event_id = str(
            data.get("_id") or data.get("_uuid") or data.get("id") or ""
        ) or None

    try:
        from ..worker import process_webhook_task
        correlation_id = uuid.uuid4().hex
        process_webhook_task.delay(
            connector.connector_id, raw_body.hex(), source_event_id
        )
        return {
            "accepted": True,
            "correlation_id": correlation_id,
            "status": "queued",
        }
    except Exception:
        _logger.debug("Celery unavailable, processing webhook inline")

    async with get_session_factory()() as session:
        run = await _ingestion.process_record(
            connector=connector,
            source_event_id=source_event_id,
            raw_data=data,
            session=session,
        )
        await session.commit()

    return {
        "run_id": run.run_id,
        "status": run.status.value,
        "registry_correlation_id": run.registry_correlation_id,
    }


async def _handle_websub_challenge(
    identifier: str, request: Request, *, by_slug: bool = False
) -> Response:
    """Echo WebSub verification challenges for active push connectors."""
    await _resolve_connector(identifier, by_slug=by_slug)

    mode = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")
    if mode not in {"subscribe", "unsubscribe"} or challenge is None:
        raise HTTPException(400, "Invalid WebSub verification request")

    return Response(content=challenge, media_type="text/plain")


# WebSub hubs (e.g. mosip/kafkaHub) sometimes append "/" on POST delivery
# even when the subscriber registered the callback without one. Accept both
# variants so FastAPI's default 307 redirect doesn't break hub deliveries
# (the hub does not follow 3xx and treats them as content-delivery errors).
@router.post("/{connector_id}", include_in_schema=True)
@router.post("/{connector_id}/", include_in_schema=False)
async def receive_webhook(connector_id: str, request: Request):
    return await _handle_webhook(connector_id, request, by_slug=False)


@router.get("/{connector_id}", include_in_schema=True)
@router.get("/{connector_id}/", include_in_schema=False)
async def verify_websub_subscription(connector_id: str, request: Request):
    return await _handle_websub_challenge(connector_id, request, by_slug=False)


@router.post("/by-slug/{slug}", include_in_schema=True)
@router.post("/by-slug/{slug}/", include_in_schema=False)
async def receive_webhook_by_slug(slug: str, request: Request):
    return await _handle_webhook(slug, request, by_slug=True)


@router.get("/by-slug/{slug}", include_in_schema=True)
@router.get("/by-slug/{slug}/", include_in_schema=False)
async def verify_websub_subscription_by_slug(slug: str, request: Request):
    return await _handle_websub_challenge(slug, request, by_slug=True)
