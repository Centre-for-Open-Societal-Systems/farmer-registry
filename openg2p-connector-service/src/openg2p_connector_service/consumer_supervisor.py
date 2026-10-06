"""Supervisor process for event-based consumers.

Run via:  ``python -m openg2p_connector_service.consumer_supervisor``

Loads all enabled connectors whose ``transport_type`` is an event consumer
(``kafka_consumer``, ``rabbit_consumer``, ``sqs``, etc.) and runs their
``iter_messages`` loops concurrently via ``asyncio.gather``.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from .config import get_settings
from .database import get_engine
from .models import ConnectorDefinition
from .services import IngestionService
from .transports import get_transport
from .transports.events.base import BaseEventConsumer

_logger = logging.getLogger("connector.consumer_supervisor")

_EVENT_TRANSPORT_TYPES = frozenset({"kafka_consumer", "rabbit_consumer", "sqs"})


async def _consume_loop(connector: ConnectorDefinition) -> None:
    """Run a single consumer loop for one connector, with restarts on failure."""
    ingestion = IngestionService()
    transport = get_transport(connector.transport_type)
    if not isinstance(transport, BaseEventConsumer):
        _logger.error(
            "Transport %s for connector %s is not an event consumer",
            connector.transport_type,
            connector.connector_id,
        )
        return

    engine = get_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    backoff = 1.0

    while True:
        try:
            _logger.info(
                "Starting consumer for connector=%s transport=%s",
                connector.connector_id,
                connector.transport_type,
            )
            async for record in transport.iter_messages(connector):
                async with session_factory() as session:
                    fresh = await session.get(
                        ConnectorDefinition, connector.connector_id
                    )
                    if fresh is None or not fresh.is_active:
                        _logger.info(
                            "Connector %s disabled, stopping consumer",
                            connector.connector_id,
                        )
                        return

                    await ingestion.process_record(
                        connector=fresh,
                        source_event_id=record.source_event_id,
                        raw_data=record.data,
                        session=session,
                    )
                    await session.commit()
                backoff = 1.0
        except asyncio.CancelledError:
            break
        except Exception:
            _logger.exception(
                "Consumer for %s crashed, restarting in %.0fs",
                connector.connector_id,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)

            async with session_factory() as session:
                connector = await session.get(  # type: ignore[assignment]
                    ConnectorDefinition, connector.connector_id
                )
                if connector is None or not connector.is_active:
                    return


async def run_supervisor() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Ensure DB tables exist
    async with get_engine().begin() as conn:
        from .models import Base
        await conn.run_sync(Base.metadata.create_all)

    engine = get_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        result = await session.execute(
            select(ConnectorDefinition).where(
                ConnectorDefinition.enabled.is_(True),
                ConnectorDefinition.paused.is_(False),
                ConnectorDefinition.transport_type.in_(list(_EVENT_TRANSPORT_TYPES)),
            )
        )
        connectors = list(result.scalars().all())

    if not connectors:
        _logger.info("No event consumers configured, exiting")
        return

    _logger.info(
        "Starting %d event consumer(s): %s",
        len(connectors),
        [c.connector_id for c in connectors],
    )
    await asyncio.gather(*[_consume_loop(c) for c in connectors])


def main() -> None:
    asyncio.run(run_supervisor())


if __name__ == "__main__":
    main()
