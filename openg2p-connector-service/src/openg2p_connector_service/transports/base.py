from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from ..models import ConnectorDefinition
from .checkpoints import Checkpoint, CheckpointMode, TransportCapability


class SourceRecord:
    """A single record fetched by a transport.

    Transports that support incremental polling should set
    ``checkpoint`` so the worker can advance ``poll_state_json`` in a
    transport-defined way (sequence id, timestamp + boundary ids, opaque
    page token…).

    The legacy ``cursor_key`` / ``cursor_value`` fields are kept for
    backward compatibility — when present without ``checkpoint``, the
    worker will treat them as a :class:`CheckpointMode.SEQUENCE`
    checkpoint stored under ``cursor_key`` in ``poll_state_json``.
    """

    def __init__(
        self,
        source_event_id: str,
        data: dict[str, Any],
        cursor_key: str | None = None,
        cursor_value: str | None = None,
        checkpoint: Checkpoint | None = None,
    ):
        self.source_event_id = source_event_id
        self.data = data
        self.cursor_key = cursor_key
        self.cursor_value = cursor_value
        self.checkpoint = checkpoint


class BaseTransport(ABC):
    """Interface every transport must implement.

    Subclasses should set :attr:`capability` to declare which checkpoint
    modes they support so the registry can answer enterprise readiness
    questions without needing to instantiate the transport.
    """

    #: Declared checkpoint capability for this transport. Defaults to
    #: ``FULL_SCAN`` so a transport that forgets to set it is treated as
    #: unsafe for strict incremental polling — callers must opt in.
    capability: TransportCapability = TransportCapability(
        modes=(CheckpointMode.FULL_SCAN,),
        default_mode=CheckpointMode.FULL_SCAN,
        supports_strict_incremental=False,
        notes="Transport did not declare a capability; assumed full-scan.",
    )

    @abstractmethod
    async def fetch(
        self, connector: ConnectorDefinition
    ) -> AsyncIterator[SourceRecord]:
        """Yield records from the external source."""
        ...
