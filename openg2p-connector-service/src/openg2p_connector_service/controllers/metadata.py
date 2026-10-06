"""Read-only metadata endpoints for UI dropdowns.

These endpoints let the Connector UI populate required form fields
(``g2p_sender_id``, ``g2p_register_mnemonic``) with dropdowns sourced from
the registry, so users can't type a mnemonic that doesn't exist.

Each endpoint uses a dedicated async engine pointed at the registry's
databases via ``CONNECTOR_MASTER_DATA_DB_DSN`` / ``CONNECTOR_REGISTRY_DB_DSN``.
If either DSN is blank the endpoint returns ``[]`` — the UI should then
degrade to a free-text input with a warning.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ..config import get_settings
from ..transports import get_transport_capability, transport_registry

router = APIRouter(prefix="/metadata", tags=["metadata"])
_logger = logging.getLogger("connector.metadata")


_master_engine: AsyncEngine | None = None
_registry_engine: AsyncEngine | None = None


def _engine_for(dsn: str, cache_key: str) -> AsyncEngine | None:
    """Return a cached read-only async engine, or None if DSN is blank."""
    global _master_engine, _registry_engine
    if not dsn:
        return None
    if cache_key == "master":
        if _master_engine is None:
            _master_engine = create_async_engine(dsn, pool_pre_ping=True, pool_size=2)
        return _master_engine
    if cache_key == "registry":
        if _registry_engine is None:
            _registry_engine = create_async_engine(dsn, pool_pre_ping=True, pool_size=2)
        return _registry_engine
    return None


@router.get("/partners")
async def list_partners() -> dict[str, Any]:
    """Return active partners from master-data DB.

    Response shape::

        {"configured": bool, "items": [{"value": "mnemonic", "label": "..."}]}

    ``configured=false`` signals the UI that the DSN isn't set.
    """
    settings = get_settings()
    engine = _engine_for(settings.master_data_db_dsn, "master")
    if engine is None:
        return {"configured": False, "items": []}

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT partner_mnemonic FROM g2p_partners "
                    "WHERE is_active = true ORDER BY partner_mnemonic"
                )
            )
            items = [
                {"value": row[0], "label": row[0]} for row in result.fetchall()
            ]
    except SQLAlchemyError:
        _logger.exception("Failed to read partners")
        return {"configured": True, "items": [], "error": "query_failed"}

    return {"configured": True, "items": items}


@router.get("/transports")
async def list_transports() -> dict[str, Any]:
    """Return registered transports with their checkpoint capabilities.

    The UI uses this to warn operators when a connector is configured
    on a transport that cannot do strict incremental polling, and to
    display the global ``strict_incremental`` policy alongside.
    """
    settings = get_settings()
    items: list[dict[str, Any]] = []
    for name in sorted(transport_registry.keys()):
        cap = get_transport_capability(name)
        items.append(
            {
                "transport_type": name,
                "modes": [m.value for m in cap.modes],
                "default_mode": cap.default_mode.value,
                "supports_strict_incremental": cap.supports_strict_incremental,
                "notes": cap.notes,
            }
        )
    return {
        "items": items,
        "policy": {
            "strict_incremental": settings.strict_incremental,
            "full_scan_on_incremental_unsupported": settings.full_scan_on_incremental_unsupported,
        },
    }


@router.get("/registers")
async def list_registers() -> dict[str, Any]:
    """Return register definitions from registry DB."""
    settings = get_settings()
    engine = _engine_for(settings.registry_db_dsn, "registry")
    if engine is None:
        return {"configured": False, "items": []}

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT register_mnemonic, COALESCE(register_subject, register_mnemonic) "
                    "FROM g2p_register_definitions ORDER BY register_mnemonic"
                )
            )
            items = [
                {"value": row[0], "label": f"{row[0]} — {row[1]}" if row[1] else row[0]}
                for row in result.fetchall()
            ]
    except SQLAlchemyError:
        _logger.exception("Failed to read registers")
        return {"configured": True, "items": [], "error": "query_failed"}

    return {"configured": True, "items": items}
