"""Publish a farmer again once it has its functional id, when its first notice went out without it.

Upstream gap (registry-platform): the intake ingest worker inserts a register row with the
placeholder functional_record_id "TEMP-<hex>", queues the id allocation and fans out
outgestion from that row at once. The functional-id allocation worker later writes the FR- id
on the live row, but never fans out again. So every farmer's first notice carries TEMP-, and
the Crop and Livestock receivers refuse it (their farmer_id must be FR- and 12 digits). Only a
later approved change, which fans out from the live row, sends the FR- id.

This task closes that gap without touching platform code or tables directly. It finds Farmer
rows whose live functional id is FR- while every outgestion snapshot of them carries TEMP-,
and fans out once more through the platform's own fanout_outgest_rows, from the live row.
The platform's transformation and publish workers then send the notice as usual.

The platform keys an outgestion payload by "<source id>:<register id>:<internal record id>".
There is no change request behind a re-publish, so the source id is a re-publish id,
"republish-fr-id:<internal record id>", passed in change_request_id (the payload tables have no
foreign key on it). That id names the farmer only once, so a farmer is re-published at most once.
The notice's event_id carries the functional id (see the templates), so the FR- notice never
shares an event id with the TEMP- one, and a receiver that drops known event ids keeps it.

The worker registers the task, and the beat producer schedules it on the worker queue. Both
processes import this module through CELERY_IMPORTS (worker.py).
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime

_logger = logging.getLogger(__name__)

TASK_NAME = "farmer_fr_id_republish_worker"
SCHEDULE_KEY = "farmer_fr_id_republish_beat_producer"
SCHEDULE_SECONDS = 300
BATCH_SIZE = 20
FARMER_REGISTER_ID = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"
SOURCE_PREFIX = "republish-fr-id:"
CHANGED_BY = "system:republish-fr-id"

# Farmers with an FR- id now whose every snapshot carries TEMP-, and no re-publish payload yet.
# Random order: a farmer whose fan-out keeps failing (logged as a warning on every run) never
# keeps the others out of the batch.
PENDING_SQL = """
SELECT f.internal_record_id
FROM g2p_register_farmers f
WHERE f.functional_record_id LIKE 'FR-%'
  AND EXISTS (
    SELECT 1 FROM outgoing_raw_data o
    JOIN outgoing_raw_data_payloads p ON p.payload_id = o.payload_id
    WHERE o.register_id = :register_id AND o.internal_record_id = f.internal_record_id
      AND p.raw_data_json ->> 'functional_record_id' LIKE 'TEMP-%')
  AND NOT EXISTS (
    SELECT 1 FROM outgoing_raw_data o
    JOIN outgoing_raw_data_payloads p ON p.payload_id = o.payload_id
    WHERE o.register_id = :register_id AND o.internal_record_id = f.internal_record_id
      AND p.raw_data_json ->> 'functional_record_id' = f.functional_record_id)
  AND NOT EXISTS (
    SELECT 1 FROM outgoing_raw_data_payloads p
    WHERE p.payload_id = :prefix || f.internal_record_id || ':' || :register_id || ':' || f.internal_record_id)
ORDER BY random()
LIMIT :limit
"""


def source_id(internal_record_id: str) -> str:
    return f"{SOURCE_PREFIX}{internal_record_id}"


def payload_id(internal_record_id: str, register_id: str = FARMER_REGISTER_ID) -> str:
    """The payload id fanout_outgest_rows gives the re-publish (its own formula)."""
    return f"{source_id(internal_record_id)}:{register_id}:{internal_record_id}"


def pending_params(limit: int = BATCH_SIZE) -> dict:
    return {"register_id": FARMER_REGISTER_ID, "prefix": SOURCE_PREFIX, "limit": limit}


def add_schedule(beat_app, worker_queue: str) -> None:
    """Add the task to the beat producer's schedule; the native entries stay as they are."""
    schedule = dict(beat_app.conf.beat_schedule or {})
    schedule[SCHEDULE_KEY] = {"task": TASK_NAME, "schedule": SCHEDULE_SECONDS,
                              "options": {"queue": worker_queue}}
    beat_app.conf.beat_schedule = schedule


async def _republish(session_maker) -> int:
    from openg2p_registry_core.models import G2PRegisterDefinition
    from openg2p_registry_core.services.g2p_outgest_fanout_service import (
        fanout_outgest_rows,
    )
    from sqlalchemy import select, text

    from .register_domain.models import G2PRegisterFarmer

    done = 0
    async with session_maker() as session:
        ids = (await session.execute(text(PENDING_SQL), pending_params())).scalars().all()
        if not ids:
            return 0
        definition = (await session.execute(select(G2PRegisterDefinition).where(
            G2PRegisterDefinition.register_id == FARMER_REGISTER_ID))).scalar_one()
        for internal_record_id in ids:
            row = (await session.execute(select(G2PRegisterFarmer).where(
                G2PRegisterFarmer.internal_record_id == internal_record_id))).scalar_one()
            try:
                await fanout_outgest_rows(
                    definition, row, session,
                    changed_by=CHANGED_BY,
                    changed_at=datetime.now(UTC).replace(tzinfo=None),
                    approved_by=getattr(row, "last_approved_by", None),
                    approved_at=getattr(row, "last_approved_at", None),
                    change_request_id=source_id(internal_record_id))
                await session.commit()
                done += 1
                _logger.info("Re-published farmer %s with functional id %s",
                             internal_record_id, row.functional_record_id)
            except Exception:  # one farmer must not stop the batch; the next run retries it
                await session.rollback()
                _logger.warning("Re-publishing farmer %s failed", internal_record_id, exc_info=True)
    return done


def _register_worker_task(worker_app) -> None:
    state = {}

    def session_maker():
        # A connection per run (NullPool): the platform's tasks each run their own event loop,
        # and pooled asyncpg connections must not cross loops. The database settings are the
        # worker's own (its Engine's datasource), so no setting or Secret is added.
        if "maker" not in state:
            from openg2p_registry_celery_worker.engine import Engine
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
            from sqlalchemy.pool import NullPool

            engine = create_async_engine(Engine.construct_async_db_datasource(), poolclass=NullPool)
            state["maker"] = async_sessionmaker(bind=engine, expire_on_commit=False)
        return state["maker"]()

    @worker_app.task(name=TASK_NAME)
    def farmer_fr_id_republish_worker():
        loop = asyncio.new_event_loop()
        try:
            done = loop.run_until_complete(_republish(session_maker))
        finally:
            loop.close()
        if done:
            _logger.info("Re-published %d farmer(s) with their functional id", done)
        return done


_installed: dict = {}


def install() -> None:
    """Register the task in the worker, or schedule it in the beat producer. Idempotent."""
    worker = sys.modules.get("openg2p_registry_celery_worker.app")
    if worker is not None and not _installed.get("worker"):
        _register_worker_task(worker.celery_app)
        _installed["worker"] = True
    beat = sys.modules.get("openg2p_registry_celery_beat.app")
    if beat is not None:
        from openg2p_registry_celery_beat.config import Settings

        add_schedule(beat.celery_app, Settings.get_config().worker_queue)
