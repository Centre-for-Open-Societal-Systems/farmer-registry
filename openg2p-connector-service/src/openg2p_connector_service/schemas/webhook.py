from typing import Any

from pydantic import BaseModel


class WebhookPayload(BaseModel):
    source_event_id: str | None = None
    data: dict[str, Any]
