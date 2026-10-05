"""Kafka consumer transport (``aiokafka``)."""

import json
import logging
from typing import AsyncIterator

import jmespath

from ...models import ConnectorDefinition
from ..base import SourceRecord
from ..checkpoints import CheckpointMode, TransportCapability
from ..registry import register_transport
from .base import BaseEventConsumer

_logger = logging.getLogger("connector.transport.kafka")


@register_transport("kafka_consumer")
class KafkaEventConsumer(BaseEventConsumer):
    # Kafka uses broker-managed offsets; we treat that as a first-class
    # PAGE_TOKEN-style cursor that the consumer commits itself rather
    # than re-using poll_state_json.
    capability = TransportCapability(
        modes=(CheckpointMode.PAGE_TOKEN,),
        default_mode=CheckpointMode.PAGE_TOKEN,
        supports_strict_incremental=True,
        notes="Kafka consumer group offsets — committed by the broker, not by poll_state_json.",
    )

    """Consume messages from a Kafka topic and yield them as SourceRecords.

    Required ``source_config_json`` keys::

        {
            "bootstrap_servers": "broker1:9092,broker2:9092",
            "topic": "partner-events",
            "consumer_group": "connector-grp",
            "value_format": "json",            // only json supported today
            "idempotency_key_path": "id",       // optional JMESPath
            "max_poll_records": 100             // optional
        }
    """

    def __init__(self) -> None:
        self._consumer = None

    async def iter_messages(
        self, connector: ConnectorDefinition
    ) -> AsyncIterator[SourceRecord]:
        try:
            from aiokafka import AIOKafkaConsumer
        except ImportError as exc:
            raise ImportError(
                "aiokafka is required for kafka_consumer transport but failed to import."
            ) from exc

        cfg = connector.get_source_config()
        bootstrap = cfg.get("bootstrap_servers", "localhost:9092")
        topic = cfg["topic"]
        group = cfg.get("consumer_group", f"connector-{connector.connector_id}")
        max_poll = cfg.get("max_poll_records", 100)
        id_path = cfg.get("idempotency_key_path")

        secrets = connector.get_auth_secrets()
        kwargs: dict = {}
        if secrets.get("sasl_mechanism"):
            kwargs["sasl_mechanism"] = secrets["sasl_mechanism"]
            kwargs["sasl_plain_username"] = secrets.get("username", "")
            kwargs["sasl_plain_password"] = secrets.get("password", "")
            kwargs["security_protocol"] = secrets.get(
                "security_protocol", "SASL_PLAINTEXT"
            )

        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=bootstrap,
            group_id=group,
            max_poll_records=max_poll,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            **kwargs,
        )
        self._consumer = consumer
        await consumer.start()
        try:
            async for msg in consumer:
                try:
                    value = json.loads(msg.value) if isinstance(msg.value, (bytes, bytearray)) else msg.value
                except (json.JSONDecodeError, TypeError):
                    _logger.warning(
                        "Skipping non-JSON message topic=%s partition=%d offset=%d",
                        msg.topic, msg.partition, msg.offset,
                    )
                    await consumer.commit()
                    continue

                source_id = None
                if id_path and isinstance(value, dict):
                    source_id = str(jmespath.search(id_path, value) or "")
                if not source_id:
                    source_id = f"{msg.topic}:{msg.partition}:{msg.offset}"

                yield SourceRecord(source_event_id=source_id, data=value if isinstance(value, dict) else {"_raw": value})
                await consumer.commit()
        finally:
            await consumer.stop()
            self._consumer = None

    async def close(self) -> None:
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None

    # BaseTransport compatibility: not a poller
    async def fetch(self, connector):  # type: ignore[override]
        raise NotImplementedError(
            "KafkaEventConsumer uses iter_messages, not fetch"
        )
