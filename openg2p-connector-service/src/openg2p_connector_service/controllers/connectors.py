from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, func, select

from ..auth.registry import auth_registry
from ..database import get_session_factory
from ..models import DeadLetterEntry, IdempotencyKey, IngestionRun, RunStatus
from ..schemas import ConnectorCreate, ConnectorRead, ConnectorUpdate
from ..services import ConnectorService
from ..transports.registry import transport_registry
from ..webhooks.verifiers import verifier_registry

router = APIRouter(prefix="/connectors", tags=["connectors"])
_service = ConnectorService()

_TRANSPORT_HINTS = {
    "webhook": "webhook",
    "websub": "webhook",
    "odk_central": "poll",
    "kafka_consumer": "consumer",
    "rabbit_consumer": "consumer",
    "sqs": "consumer",
}
_PUSH_TRANSPORTS = frozenset({"webhook", "websub"})


@router.get("/meta")
async def connector_meta():
    """Machine-readable options for building create/edit forms."""
    return {
        "transport_types": list(transport_registry.keys()),
        "auth_types": list(auth_registry.keys()),
        "webhook_verifiers": list(verifier_registry.keys()),
        "transport_hints": {
            k: _TRANSPORT_HINTS.get(k, "poll")
            for k in transport_registry
        },
    }


@router.get("", response_model=list[ConnectorRead])
async def list_connectors():
    async with get_session_factory()() as session:
        return await _service.list_all(session)


@router.get("/{connector_id}", response_model=ConnectorRead)
async def get_connector(connector_id: str):
    async with get_session_factory()() as session:
        cd = await _service.get(connector_id, session)
        if cd is None:
            raise HTTPException(404, "Connector not found")
        return ConnectorRead.model_validate(cd)


@router.post("", response_model=ConnectorRead, status_code=201)
async def create_connector(data: ConnectorCreate):
    async with get_session_factory()() as session:
        cd = await _service.create(data, session)
        await session.commit()
        await session.refresh(cd)
        return ConnectorRead.model_validate(cd)


@router.patch("/{connector_id}", response_model=ConnectorRead)
async def update_connector(connector_id: str, data: ConnectorUpdate):
    async with get_session_factory()() as session:
        cd = await _service.update(connector_id, data, session)
        if cd is None:
            raise HTTPException(404, "Connector not found")
        await session.commit()
        await session.refresh(cd)
        return ConnectorRead.model_validate(cd)


@router.delete("/{connector_id}", status_code=204)
async def delete_connector(connector_id: str):
    async with get_session_factory()() as session:
        ok = await _service.delete(connector_id, session)
        if not ok:
            raise HTTPException(404, "Connector not found")
        await session.commit()


@router.get("/{connector_id}/stats")
async def connector_stats(connector_id: str):
    """Operational snapshot: last poll, run counts by status, DLQ count, next poll ETA."""
    async with get_session_factory()() as session:
        cd = await _service.get(connector_id, session)
        if cd is None:
            raise HTTPException(404, "Connector not found")

        status_rows = await session.execute(
            select(IngestionRun.status, func.count()).where(
                IngestionRun.connector_id == connector_id
            ).group_by(IngestionRun.status)
        )
        status_counts = {s.value: n for s, n in status_rows.all()}
        for s in RunStatus:
            status_counts.setdefault(s.value, 0)

        dlq_count = (
            await session.execute(
                select(func.count()).select_from(DeadLetterEntry).where(
                    DeadLetterEntry.connector_id == connector_id
                )
            )
        ).scalar_one()

        last_run_stmt = (
            select(IngestionRun)
            .where(IngestionRun.connector_id == connector_id)
            .order_by(IngestionRun.updated_at.desc())
            .limit(1)
        )
        last_run = (await session.execute(last_run_stmt)).scalar_one_or_none()

        cfg = cd.get_source_config()
        interval = int(cfg.get("poll_interval_seconds") or 0) or None
        next_poll_at = None
        if interval and cd.last_poll_at:
            last = cd.last_poll_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            next_poll_at = last.timestamp() + interval
            next_poll_at = datetime.fromtimestamp(next_poll_at, tz=timezone.utc)

        return {
            "connector_id": connector_id,
            "is_active": cd.is_active,
            "last_poll_at": cd.last_poll_at,
            "last_poll_status": cd.last_poll_status,
            "last_poll_error": cd.last_poll_error,
            "last_poll_fetched": cd.last_poll_fetched,
            "last_poll_duration_ms": cd.last_poll_duration_ms,
            "poll_interval_seconds": interval,
            "next_poll_at": next_poll_at,
            "dlq_count": int(dlq_count or 0),
            "run_status_counts": status_counts,
            "total_runs": sum(status_counts.values()),
            "poll_state": cd.get_poll_state(),
            "last_run": {
                "run_id": last_run.run_id,
                "status": last_run.status.value,
                "source_event_id": last_run.source_event_id,
                "registry_correlation_id": last_run.registry_correlation_id,
                "last_error": last_run.last_error,
                "created_at": last_run.created_at,
                "updated_at": last_run.updated_at,
            } if last_run else None,
        }


@router.post("/{connector_id}/poll", status_code=202)
async def trigger_poll(connector_id: str):
    """Queue an immediate poll for this connector (same task beat would fire)."""
    async with get_session_factory()() as session:
        cd = await _service.get(connector_id, session)
        if cd is None:
            raise HTTPException(404, "Connector not found")
        if cd.transport_type in _PUSH_TRANSPORTS:
            raise HTTPException(400, f"{cd.transport_type} connectors are not polled")

    from ..worker import poll_connector_task
    task = poll_connector_task.delay(connector_id)
    return {"task_id": task.id, "connector_id": connector_id, "queued_at": datetime.now(timezone.utc)}


@router.post("/{connector_id}/reset-cursor", status_code=200)
async def reset_cursor(connector_id: str):
    """Clear incremental poll_state_json so the next poll re-fetches from the beginning."""
    async with get_session_factory()() as session:
        cd = await _service.get(connector_id, session)
        if cd is None:
            raise HTTPException(404, "Connector not found")
        cd.poll_state_json = None
        await session.commit()
    return {"connector_id": connector_id, "poll_state": {}}


@router.post("/{connector_id}/clear-idempotency", status_code=200)
async def clear_idempotency(connector_id: str):
    """Delete stored idempotency keys so the same source_event_id can be ingested again (e.g. retesting)."""
    async with get_session_factory()() as session:
        cd = await _service.get(connector_id, session)
        if cd is None:
            raise HTTPException(404, "Connector not found")
        result = await session.execute(
            delete(IdempotencyKey).where(IdempotencyKey.connector_id == connector_id)
        )
        deleted = int(result.rowcount or 0)
        await session.commit()
    return {"connector_id": connector_id, "idempotency_keys_deleted": deleted}


@router.post("/{connector_id}/websub/sync-subscriptions")
async def websub_sync_subscriptions(connector_id: str):
    """Register and subscribe this connector's callback with the WebSub hub (EDRMC, etc.).

    Reads ``hub_url``, ``callback_url``, and ``topics`` (or ``partner_id``) from
    ``source_config_json``; uses ``auth_secret_json`` for OAuth and ``webhook_secret``
    as ``hub.secret``. Idempotent: safe to re-run after hub restarts.
    """
    from ..services.websub_hub_sync import sync_subscriptions_with_hub

    async with get_session_factory()() as session:
        cd = await _service.get(connector_id, session)
        if cd is None:
            raise HTTPException(404, "Connector not found")
        try:
            return await sync_subscriptions_with_hub(cd)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
