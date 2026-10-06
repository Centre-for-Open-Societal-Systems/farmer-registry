from .base import BaseTransport
from .checkpoints import CheckpointMode, TransportCapability

transport_registry: dict[str, type[BaseTransport]] = {}


def register_transport(name: str):
    """Decorator to register a transport implementation."""

    def wrapper(cls: type[BaseTransport]):
        transport_registry[name] = cls
        return cls

    return wrapper


def get_transport(name: str) -> BaseTransport:
    cls = transport_registry.get(name)
    if cls is None:
        raise ValueError(f"Unknown transport: {name!r}. Registered: {list(transport_registry)}")
    return cls()


def get_transport_capability(name: str) -> TransportCapability:
    """Return the capability declaration for a registered transport.

    Raises ``ValueError`` if the transport name is unknown. The
    capability is read from the class without instantiating it so this
    is safe to call from health checks and admin endpoints.
    """
    cls = transport_registry.get(name)
    if cls is None:
        raise ValueError(f"Unknown transport: {name!r}. Registered: {list(transport_registry)}")
    cap = getattr(cls, "capability", None)
    if not isinstance(cap, TransportCapability):
        # Defensive: fall back to the safe-by-default declaration so
        # callers can still reason about it.
        return TransportCapability(
            modes=(CheckpointMode.FULL_SCAN,),
            default_mode=CheckpointMode.FULL_SCAN,
            supports_strict_incremental=False,
            notes="Transport class did not declare a capability.",
        )
    return cap
