import logging

from fastapi import APIRouter
from sqlalchemy import text

from ..database import get_session_factory

router = APIRouter(tags=["health"])
_logger = logging.getLogger("connector.controller.health")


@router.get("/health")
async def health():
    """Basic liveness probe — always responds if the process is up."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    """Readiness probe — verifies DB connectivity."""
    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        _logger.warning("Readiness check failed: %s", exc)
        return {"status": "not_ready", "error": str(exc)[:200]}
