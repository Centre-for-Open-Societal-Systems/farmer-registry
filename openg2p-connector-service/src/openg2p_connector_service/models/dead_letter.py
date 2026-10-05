import uuid

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeadLetterEntry(Base):
    __tablename__ = "dead_letter_queue"

    dl_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: uuid.uuid4().hex
    )
    connector_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_event_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_category: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
