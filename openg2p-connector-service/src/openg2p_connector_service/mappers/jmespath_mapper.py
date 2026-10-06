from typing import Any

import jmespath

from .base import BaseMapper


class JmesPathMapper(BaseMapper):
    """Applies a JMESPath expression to reshape source data to DataModel-shaped JSON."""

    def map(self, raw: dict[str, Any], expression: str | None = None) -> dict[str, Any]:
        if not expression:
            return raw
        result = jmespath.search(expression, raw)
        if not isinstance(result, dict):
            raise ValueError(f"JMESPath expression must produce a dict, got {type(result).__name__}")
        return result
