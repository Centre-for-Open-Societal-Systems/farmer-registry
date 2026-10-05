from .base import BaseTransport, SourceRecord
from .checkpoints import (
    CHECKPOINT_STATE_KEY,
    Checkpoint,
    CheckpointMode,
    TransportCapability,
)
from .registry import (
    get_transport,
    get_transport_capability,
    register_transport,
    transport_registry,
)

# Trigger self-registration of built-in transports
from . import webhook as _wh  # noqa: F401, E402
from . import websub as _websub  # noqa: F401, E402
from . import odk_central as _odk  # noqa: F401, E402

# Optional event consumers — import errors are swallowed when the
# broker client library is not installed.
try:
    from .events import kafka_consumer as _kafka  # noqa: F401
except ImportError:
    pass

__all__ = [
    "BaseTransport",
    "SourceRecord",
    "Checkpoint",
    "CheckpointMode",
    "CHECKPOINT_STATE_KEY",
    "TransportCapability",
    "transport_registry",
    "register_transport",
    "get_transport",
    "get_transport_capability",
]
