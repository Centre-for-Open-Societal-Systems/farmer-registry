"""Standard OAuth2 client-credentials flow (works for Keycloak, Auth0, etc.)."""

import logging
import time

import httpx

from ...models import ConnectorDefinition
from ..base import AuthContext, BaseAuthStrategy
from ..registry import register_auth

_logger = logging.getLogger("connector.auth.oauth2_cc")


@register_auth("oauth2_client_credentials")
class OAuth2ClientCredentialsAuth(BaseAuthStrategy):
    def __init__(self) -> None:
        self._cache: dict[str, tuple[str, float, float]] = {}

    async def get_auth_context(self, connector: ConnectorDefinition) -> AuthContext:
        cid = connector.connector_id
        now = time.monotonic()
        cached = self._cache.get(cid)
        if cached:
            token, obtained_at, expires_in = cached
            if now - obtained_at < expires_in - 30:
                return AuthContext(headers={"Authorization": f"Bearer {token}"})

        secrets = connector.get_auth_secrets()
        token_url = secrets.get("token_url", "")
        client_id = secrets.get("client_id", "")
        client_secret = secrets.get("client_secret", "")
        scope = secrets.get("scope", "")
        if not token_url or not client_id:
            raise ValueError(
                f"Connector {cid}: oauth2_client_credentials requires "
                "auth_secret_json.token_url and client_id"
            )

        data: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if scope:
            data["scope"] = scope

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(token_url, data=data)
            resp.raise_for_status()
            body = resp.json()

        token = body["access_token"]
        expires_in = float(body.get("expires_in", 3600))
        self._cache[cid] = (token, now, expires_in)
        _logger.info("OAuth2 CC token acquired for connector=%s", cid)
        return AuthContext(headers={"Authorization": f"Bearer {token}"})

    async def close(self) -> None:
        self._cache.clear()
