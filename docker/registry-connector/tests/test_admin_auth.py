"""Admin-only API: OpenG2P staff token with the connector's admin client role."""

import sys
import time
import warnings
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from openg2p_registry_connector_extension import admin_auth, startup  # noqa: E402

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient  # noqa: E402

ISSUER = "https://keycloak.example.test/realms/staff"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = {**jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True), "kid": "k1", "alg": "RS256", "use": "sig"}


def token(roles=("REGISTRY_CONNECTOR_ADMIN",), client="registry-connector", issuer=ISSUER, key=KEY, exp=300):
    claims = {"iss": issuer, "sub": "admin", "exp": int(time.time()) + exp,
              "resource_access": {client: {"roles": list(roles)}}}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture(autouse=True)
def jwks(monkeypatch):
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [JWK]})


def client(issuer=ISSUER):
    app = FastAPI()
    for path in ("/health", "/health/ready", "/metrics", "/webhook/by-slug/x", "/connectors", "/runs", "/docs-like"):
        app.add_api_route(path, lambda: {"ok": True}, methods=["GET", "POST"])
    settings = admin_auth.Settings(issuer=issuer, jwks_url=f"{issuer}/protocol/openid-connect/certs" if issuer else "",
                                   client_id="registry-connector", role="REGISTRY_CONNECTOR_ADMIN",
                                   ui_client_id="registry-connector-ui", metrics_path="/metrics")
    app.add_middleware(admin_auth.AdminAuthMiddleware, settings=settings)
    return TestClient(app)


def bearer(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.mark.parametrize("path", ["/health", "/health/ready", "/metrics", "/webhook/by-slug/x"])
def test_health_metrics_and_webhooks_stay_open(path):
    assert client().get(path).status_code == 200
    assert client(issuer="").get(path).status_code == 200


def test_admin_route_needs_a_token():
    r = client().get("/connectors")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_admin_role_opens_admin_routes():
    c = client()
    assert c.get("/connectors", headers=bearer(token())).status_code == 200
    assert c.post("/runs", headers=bearer(token())).status_code == 200


@pytest.mark.parametrize("t", [
    token(roles=("Registry Staff",)),
    token(client="staff-portal"),
])
def test_token_without_the_admin_client_role_is_forbidden(t):
    assert client().get("/connectors", headers=bearer(t)).status_code == 403


@pytest.mark.parametrize("t", [
    token(issuer="https://keycloak.example.test/realms/beneficiary"),
    token(key=OTHER),
    token(exp=-120),
    "not-a-jwt",
])
def test_foreign_forged_or_expired_token_is_rejected(t):
    assert client().get("/connectors", headers=bearer(t)).status_code == 401


def test_unconfigured_issuer_fails_closed():
    assert client(issuer="").get("/connectors", headers=bearer(token())).status_code == 503


def test_ui_login_settings_are_open():
    body = client().get(admin_auth.CONFIG_PATH).json()
    assert body == {"configured": True, "url": "https://keycloak.example.test", "realm": "staff",
                    "clientId": "registry-connector-ui", "roleClientId": "registry-connector",
                    "role": "REGISTRY_CONNECTOR_ADMIN"}


def test_settings_from_environment_then_file(monkeypatch, tmp_path):
    f = tmp_path / "admin-auth.json"
    f.write_text('{"issuer": "https://file.test/realms/staff", "role": "FILE_ROLE"}')
    monkeypatch.setenv("CONNECTOR_ADMIN_AUTH_CONFIG_FILE", str(f))
    s = admin_auth.load_settings()
    assert (s.issuer, s.role, s.jwks_url) == ("https://file.test/realms/staff", "FILE_ROLE",
                                               "https://file.test/realms/staff/protocol/openid-connect/certs")
    monkeypatch.setenv("CONNECTOR_ADMIN_AUTH_ISSUER", ISSUER)
    monkeypatch.setenv("CONNECTOR_ADMIN_AUTH_JWKS_URL", "http://keycloak.svc/realms/staff/protocol/openid-connect/certs")
    s = admin_auth.load_settings()
    assert (s.issuer, s.jwks_url, s.client_id) == (ISSUER, "http://keycloak.svc/realms/staff/protocol/openid-connect/certs",
                                                    "registry-connector")


def test_no_settings_means_not_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("CONNECTOR_ADMIN_AUTH_CONFIG_FILE", str(tmp_path / "absent.json"))
    assert admin_auth.load_settings().issuer == ""


def test_hook_guards_the_published_api_app(monkeypatch, tmp_path):
    monkeypatch.setenv("CONNECTOR_ADMIN_AUTH_CONFIG_FILE", str(tmp_path / "absent.json"))
    startup.register()  # what the .pth line does at interpreter start
    from openg2p_connector_service import main

    assert any(m.cls is admin_auth.AdminAuthMiddleware for m in main.app.user_middleware)
    admin_auth.install(main.app)
    assert sum(m.cls is admin_auth.AdminAuthMiddleware for m in main.app.user_middleware) == 1
    c = TestClient(main.app)
    assert c.get("/health").json() == {"status": "ok"}
    assert c.get("/connectors").status_code == 503  # no issuer configured: closed, never open
