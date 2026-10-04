"""Abstract base for event-stream consumers (Kafka, RabbitMQ, SQS, …)."""

from abc import ABC, abstractmethod
from typing import AsyncIterator

from ...models import ConnectorDefinition
from ..base import SourceRecord


class BaseEventConsumer(ABC):
    """Long-running consumer that yields records from a message broker."""

    @abstractmethod
    async def iter_messages(
        self, connector: ConnectorDefinition
    ) -> AsyncIterator[SourceRecord]:
        """Yield ``SourceRecord`` items from the configured broker/topic.

        The consumer is responsible for offset management; only commit after
        the caller confirms successful processing.
        """
        ...

    async def close(self) -> None:
        """Release broker connections."""
