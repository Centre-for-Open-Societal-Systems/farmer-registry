from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IdempotencyKey(Base):
    """Natural-key deduplication: (connector_id, source_key) must be unique."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("connector_id", "source_key", name="uq_idem_connector_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String(512), nullable=False)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    # How many times the same source_key was delivered again after the first
    # successful ingest (incremented on each idempotent short-circuit).
    redelivery_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
