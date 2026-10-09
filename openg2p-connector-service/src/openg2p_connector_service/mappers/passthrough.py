from typing import Any

from .base import BaseMapper


class PassthroughMapper(BaseMapper):
    """Returns data as-is — useful when source already matches the DataModel shape."""

    def map(self, raw: dict[str, Any], expression: str | None = None) -> dict[str, Any]:
        return raw
