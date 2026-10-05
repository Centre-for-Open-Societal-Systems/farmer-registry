"""ODK Central session-token auth: POST /v1/sessions with email/password."""

import logging
import time

import httpx

from ...config import get_settings
from ...models import ConnectorDefinition
from ..base import AuthContext, BaseAuthStrategy
from ..registry import register_auth

_logger = logging.getLogger("connector.auth.odk_session")

_TOKEN_TTL_SECONDS = 3600


@register_auth("odk_session")
class OdkSessionAuth(BaseAuthStrategy):
    def __init__(self) -> None:
        self._cache: dict[str, tuple[str, float]] = {}

    async def get_auth_context(self, connector: ConnectorDefinition) -> AuthContext:
        cid = connector.connector_id
        now = time.monotonic()
        cached = self._cache.get(cid)
        if cached and now - cached[1] < _TOKEN_TTL_SECONDS:
            return AuthContext(headers={"Authorization": f"Bearer {cached[0]}"})

        cfg = connector.get_source_config()
        base_url = cfg.get("base_url", "").rstrip("/")
        secrets = connector.get_auth_secrets()
        email = secrets.get("email", "")
        password = secrets.get("password", "")
        if not base_url or not email:
            raise ValueError(
                f"Connector {cid}: odk_session requires source_config_json.base_url "
                "and auth_secret_json.email/password"
            )

        timeout_sec = max(5.0, min(float(get_settings().odk_http_timeout_seconds), 300.0))
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(
                f"{base_url}/v1/sessions",
                json={"email": email, "password": password},
            )
            resp.raise_for_status()
            token = resp.json()["token"]

        self._cache[cid] = (token, now)
        _logger.info("Acquired ODK session token for connector=%s", cid)
        return AuthContext(headers={"Authorization": f"Bearer {token}"})

    async def close(self) -> None:
        self._cache.clear()
