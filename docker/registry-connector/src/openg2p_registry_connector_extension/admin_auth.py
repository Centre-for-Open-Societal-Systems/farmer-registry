"""Admin-only access to the connector's API and UI, by an OpenG2P staff client role.

The published connector has no login: every route is open to anyone who can reach it.
This follows the OpenG2P service pattern (Keycloak ``staff`` realm, a confidential
service client defining admin client roles, inbound tokens validated via JWKS), as the
Consent Manager and AWE do:

* ``/health*``, the metrics path and ``/webhook*`` stay open. Webhooks are verified by
  each connector's own verifier, and the hub delivers in-cluster.
* ``/metadata/admin-auth`` is open: it tells the UI where to log in.
* Every other route needs a bearer token from the configured issuer whose
  ``resource_access[<client_id>].roles`` holds the admin role. A missing or invalid
  token is 401, a token without the role is 403.
* Without an issuer the protected routes answer 503: the API never falls back to open.

Settings come from ``CONNECTOR_ADMIN_AUTH_*`` environment variables, then from the JSON
file named by ``CONNECTOR_ADMIN_AUTH_CONFIG_FILE`` (keys without the prefix, lower case).
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import jwt
from starlette.concurrency import run_in_threadpool

log = logging.getLogger(__name__)

CONFIG_FILE = "/etc/openg2p-registry-connector-extension/admin-auth.json"
CONFIG_PATH = "/metadata/admin-auth"
OPEN_PREFIXES = ("/health", "/webhook")
ALGORITHMS = ["RS256", "ES256", "PS256"]


@dataclass(frozen=True)
class Settings:
    issuer: str
    jwks_url: str
    client_id: str
    role: str
    ui_client_id: str
    metrics_path: str

    @property
    def keycloak_url(self) -> str:
        return self.issuer.split("/realms/", 1)[0]

    @property
    def realm(self) -> str:
        return self.issuer.split("/realms/", 1)[1].split("/", 1)[0] if "/realms/" in self.issuer else ""


def load_settings() -> Settings:
    path = os.environ.get("CONNECTOR_ADMIN_AUTH_CONFIG_FILE", CONFIG_FILE)
    try:
        stored = json.loads(Path(path).read_text())
    except FileNotFoundError:
        stored = {}

    def get(key: str, default: str = "") -> str:
        return os.environ.get(f"CONNECTOR_ADMIN_AUTH_{key.upper()}") or str(stored.get(key) or default)

    issuer = get("issuer").rstrip("/")
    return Settings(
        issuer=issuer,
        jwks_url=get("jwks_url", f"{issuer}/protocol/openid-connect/certs" if issuer else ""),
        client_id=get("client_id", "registry-connector"),
        role=get("role", "REGISTRY_CONNECTOR_ADMIN"),
        ui_client_id=get("ui_client_id", "registry-connector-ui"),
        metrics_path=os.environ.get("CONNECTOR_METRICS_PATH", "/metrics"),
    )


class _Denied(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


class AdminAuthMiddleware:
    """ASGI middleware: open routes pass, the rest need the admin client role."""

    def __init__(self, app, settings: Settings | None = None):
        self.app = app
        self.settings = settings or load_settings()
        self._jwks = jwt.PyJWKClient(self.settings.jwks_url, cache_keys=True, lifespan=300) if self.settings.jwks_url else None
        if not self.settings.issuer:
            log.warning("Connector admin auth has no issuer: admin routes answer 503")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path, method = scope["path"], scope["method"]
        if method == "OPTIONS" or self._open(path):
            return await self.app(scope, receive, send)
        if path.rstrip("/") == CONFIG_PATH:
            return await _json(send, 200, self.ui_config())
        try:
            scope.setdefault("state", {})["admin_claims"] = await self.authorize(_bearer(scope))
        except _Denied as denied:
            return await _json(send, denied.status, {"detail": denied.detail},
                               {"www-authenticate": "Bearer"} if denied.status == 401 else None)
        return await self.app(scope, receive, send)

    def _open(self, path: str) -> bool:
        return path == self.settings.metrics_path or any(
            path == p or path.startswith(p + "/") for p in OPEN_PREFIXES)

    def ui_config(self) -> dict:
        s = self.settings
        return {"configured": bool(s.issuer), "url": s.keycloak_url, "realm": s.realm, "clientId": s.ui_client_id,
                "roleClientId": s.client_id, "role": s.role}

    async def authorize(self, token: str | None) -> dict:
        s = self.settings
        if not s.issuer or self._jwks is None:
            raise _Denied(503, "Connector admin authentication is not configured")
        if not token:
            raise _Denied(401, "Bearer token required")
        try:
            key = await run_in_threadpool(self._jwks.get_signing_key_from_jwt, token)
            claims = jwt.decode(token, key.key, algorithms=ALGORITHMS, issuer=s.issuer,
                                options={"verify_aud": False, "require": ["exp", "iss"]}, leeway=30)
        except jwt.PyJWTError as exc:
            raise _Denied(401, f"Invalid token: {exc}") from None
        roles = ((claims.get("resource_access") or {}).get(s.client_id) or {}).get("roles") or []
        if s.role not in roles:
            raise _Denied(403, f"Role {s.role} on client {s.client_id} required")
        return claims


def _bearer(scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            return token.strip() if scheme.lower() == "bearer" and token.strip() else None
    return None


async def _json(send, status: int, body: dict, headers: dict | None = None) -> None:
    raw = json.dumps(body).encode()
    extra = [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode()),
                            (b"cache-control", b"no-store"), *extra]})
    await send({"type": "http.response.body", "body": raw})


_MARK = "_openg2p_registry_connector_extension_admin_auth"


def install(app) -> None:
    """Add the middleware to the connector's FastAPI app once."""
    if getattr(app.state, _MARK, False):
        return
    app.add_middleware(AdminAuthMiddleware)
    setattr(app.state, _MARK, True)
