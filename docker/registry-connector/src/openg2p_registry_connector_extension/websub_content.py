"""Read the published message out of a WebSub hub delivery."""

import json
from typing import Any


def unwrap(raw_data: dict[str, Any]) -> dict[str, Any]:
    content = raw_data.get("hub.content")
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, dict):
        raise ValueError("WebSub content must be a JSON object")
    return content
