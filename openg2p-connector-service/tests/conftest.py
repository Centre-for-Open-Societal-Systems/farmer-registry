import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("CONNECTOR_DB_DRIVER", "sqlite+aiosqlite")
os.environ.setdefault("CONNECTOR_DB_HOSTNAME", "")
os.environ.setdefault("CONNECTOR_DB_PORT", "0")
os.environ.setdefault("CONNECTOR_DB_USERNAME", "")
os.environ.setdefault("CONNECTOR_DB_PASSWORD", "")
os.environ.setdefault("CONNECTOR_DB_DBNAME", ":memory:")

from openg2p_connector_service.models import Base  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture()
async def app_client():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    import openg2p_connector_service.database as db_mod

    db_mod._engine = engine
    db_mod._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    mock_send = AsyncMock(return_value="test-correlation-id")
    with patch(
        "openg2p_connector_service.services.ingestion_service.PartnerIngestClient.send",
        mock_send,
    ):
        from openg2p_connector_service.main import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
