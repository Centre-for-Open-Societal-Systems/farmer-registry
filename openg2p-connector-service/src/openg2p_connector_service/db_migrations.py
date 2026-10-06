"""Idempotent in-process schema upgrades.

We don't ship Alembic yet, so evolving columns on ``connector_definitions``
is handled here. Each step is ``ADD COLUMN IF NOT EXISTS`` so it's safe to
run on every startup and on every worker boot.

Keep this lean — anything non-trivial should graduate to a real migration
tool.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_logger = logging.getLogger("connector.db.migrations")

_STEPS: list[str] = [
    "ALTER TABLE connector_definitions "
    "ADD COLUMN IF NOT EXISTS g2p_sender_id VARCHAR(128)",
    "ALTER TABLE connector_definitions "
    "ADD COLUMN IF NOT EXISTS g2p_register_mnemonic VARCHAR(128)",
    "ALTER TABLE idempotency_keys "
    "ADD COLUMN IF NOT EXISTS redelivery_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ingestion_runs "
    "ADD COLUMN IF NOT EXISTS redelivery_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ingestion_runs "
    "ADD COLUMN IF NOT EXISTS run_payload_json TEXT",
]


async def apply(conn: AsyncConnection) -> None:
    for stmt in _STEPS:
        try:
            await conn.execute(text(stmt))
        except Exception:
            _logger.exception("Failed DDL: %s", stmt)
            raise
