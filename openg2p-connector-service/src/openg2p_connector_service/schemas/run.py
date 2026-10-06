from datetime import datetime
from typing import Any

from pydantic import BaseModel


class IngestionRunRead(BaseModel):
    run_id: str
    connector_id: str
    source_event_id: str | None = None
    correlation_id: str | None = None
    status: str
    attempt_count: int
    last_error: str | None = None
    registry_correlation_id: str | None = None
    redelivery_count: int = 0
    connector_name: str | None = None
    run_payload: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RunsPage(BaseModel):
    items: list[IngestionRunRead]
    total: int


class DLQEntryRead(BaseModel):
    dl_id: str
    connector_id: str
    source_event_id: str | None = None
    payload: dict[str, Any] | None = None
    error: str | None = None
    error_category: str | None = None
    attempt_count: int
    connector_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DLQPage(BaseModel):
    items: list[DLQEntryRead]
    total: int


class ReplayRequest(BaseModel):
    dl_ids: list[str]
