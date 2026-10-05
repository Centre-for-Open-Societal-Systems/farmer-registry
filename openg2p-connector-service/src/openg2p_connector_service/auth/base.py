from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..models import ConnectorDefinition


@dataclass
class AuthContext:
    """Credentials resolved for a single outbound request."""

    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    base_url: str | None = None


class BaseAuthStrategy(ABC):
    @abstractmethod
    async def get_auth_context(self, connector: ConnectorDefinition) -> AuthContext:
        ...

    async def close(self) -> None:
        """Release any cached resources (tokens, sessions)."""
