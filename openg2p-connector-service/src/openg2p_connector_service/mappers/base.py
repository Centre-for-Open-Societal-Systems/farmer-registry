from abc import ABC, abstractmethod
from typing import Any


class BaseMapper(ABC):
    """Transform a source record's data into the shape expected by the registry DataModel."""

    @abstractmethod
    def map(self, raw: dict[str, Any], expression: str | None = None) -> dict[str, Any]:
        ...
