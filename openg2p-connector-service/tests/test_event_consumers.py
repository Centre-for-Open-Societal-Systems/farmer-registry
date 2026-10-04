"""Smoke tests for event consumer transport registration and interface."""

import pytest
from unittest.mock import MagicMock

from openg2p_connector_service.transports.events.base import BaseEventConsumer


class DummyConsumer(BaseEventConsumer):
    """In-memory consumer for testing the abstract interface."""

    def __init__(self, records):
        self._records = records

    async def iter_messages(self, connector):
        for r in self._records:
            yield r


@pytest.mark.asyncio
async def test_dummy_consumer_yields_records():
    from openg2p_connector_service.transports.base import SourceRecord

    records = [
        SourceRecord(source_event_id="ev1", data={"a": 1}),
        SourceRecord(source_event_id="ev2", data={"b": 2}),
    ]
    consumer = DummyConsumer(records)
    connector = MagicMock()
    collected = []
    async for rec in consumer.iter_messages(connector):
        collected.append(rec)
    assert len(collected) == 2
    assert collected[0].source_event_id == "ev1"


def test_kafka_consumer_import_error():
    """KafkaEventConsumer is registered only when aiokafka is available."""
    try:
        import aiokafka  # noqa: F401
        from openg2p_connector_service.transports import get_transport
        transport = get_transport("kafka_consumer")
        assert transport is not None
    except ImportError:
        pass
