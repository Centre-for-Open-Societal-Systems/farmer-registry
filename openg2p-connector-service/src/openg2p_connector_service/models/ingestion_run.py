import enum
import uuid

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RunStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    run_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: uuid.uuid4().hex
    )
    connector_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )
    source_event_id: Mapped[str | None] = mapped_column(
        String(512), nullable=True, index=True
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus), default=RunStatus.PENDING, nullable=False, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    registry_correlation_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    # Mirrored from IdempotencyKey.redelivery_count for list/detail reads.
    redelivery_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    # Optional JSON blob for debugging (source / mapped / outbound); gated by config.
    run_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
