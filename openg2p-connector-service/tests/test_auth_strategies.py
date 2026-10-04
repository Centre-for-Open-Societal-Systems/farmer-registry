"""Unit tests for the pluggable auth strategy registry."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from openg2p_connector_service.auth import get_auth_strategy
from openg2p_connector_service.auth.strategies.none_auth import NoneAuth
from openg2p_connector_service.auth.strategies.static_bearer import StaticBearerAuth
from openg2p_connector_service.auth.strategies.odk_session import OdkSessionAuth
from openg2p_connector_service.auth.strategies.oauth2_client_credentials import (
    OAuth2ClientCredentialsAuth,
)
from openg2p_connector_service.auth.strategies.oauth2_password import OAuth2PasswordAuth


def _connector(
    auth_type: str = "none",
    source_config: dict | None = None,
    auth_secrets: dict | None = None,
) -> MagicMock:
    c = MagicMock()
    c.connector_id = "test-connector"
    c.auth_type = auth_type
    c.get_source_config.return_value = source_config or {}
    c.get_auth_secrets.return_value = auth_secrets or {}
    return c


def test_registry_resolves():
    assert isinstance(get_auth_strategy("none"), NoneAuth)
    assert isinstance(get_auth_strategy("static_bearer"), StaticBearerAuth)
    assert isinstance(get_auth_strategy("odk_session"), OdkSessionAuth)
    assert isinstance(get_auth_strategy("oauth2_client_credentials"), OAuth2ClientCredentialsAuth)
    assert isinstance(get_auth_strategy("oauth2_password"), OAuth2PasswordAuth)


@pytest.mark.asyncio
async def test_none_auth():
    ctx = await NoneAuth().get_auth_context(_connector())
    assert ctx.headers == {}


@pytest.mark.asyncio
async def test_static_bearer():
    ctx = await StaticBearerAuth().get_auth_context(
        _connector(auth_secrets={"token": "tok123"})
    )
    assert ctx.headers == {"Authorization": "Bearer tok123"}


@pytest.mark.asyncio
async def test_static_bearer_missing_token():
    with pytest.raises(ValueError, match="token is empty"):
        await StaticBearerAuth().get_auth_context(_connector())


@pytest.mark.asyncio
async def test_odk_session():
    mock_response = MagicMock()
    mock_response.json.return_value = {"token": "odk-token-xyz"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("openg2p_connector_service.auth.strategies.odk_session.httpx.AsyncClient", return_value=mock_client):
        strategy = OdkSessionAuth()
        ctx = await strategy.get_auth_context(
            _connector(
                source_config={"base_url": "https://odk.example.com"},
                auth_secrets={"email": "admin@x.com", "password": "pass"},
            )
        )
    assert ctx.headers == {"Authorization": "Bearer odk-token-xyz"}


@pytest.mark.asyncio
async def test_oauth2_client_credentials():
    mock_response = MagicMock()
    mock_response.json.return_value = {"access_token": "cc-tok", "expires_in": 3600}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "openg2p_connector_service.auth.strategies.oauth2_client_credentials.httpx.AsyncClient",
        return_value=mock_client,
    ):
        strategy = OAuth2ClientCredentialsAuth()
        ctx = await strategy.get_auth_context(
            _connector(
                auth_secrets={
                    "token_url": "https://auth.example.com/token",
                    "client_id": "cid",
                    "client_secret": "csec",
                }
            )
        )
    assert ctx.headers == {"Authorization": "Bearer cc-tok"}


@pytest.mark.asyncio
async def test_oauth2_password():
    mock_response = MagicMock()
    mock_response.json.return_value = {"access_token": "pw-tok", "expires_in": 1800}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "openg2p_connector_service.auth.strategies.oauth2_password.httpx.AsyncClient",
        return_value=mock_client,
    ):
        strategy = OAuth2PasswordAuth()
        ctx = await strategy.get_auth_context(
            _connector(
                auth_secrets={
                    "token_url": "https://auth.example.com/token",
                    "client_id": "cid",
                    "username": "user",
                    "password": "pass",
                }
            )
        )
    assert ctx.headers == {"Authorization": "Bearer pw-tok"}
