"""Guard: the iam_core permission-lookup patch applies and does what it says.

docker/patches/patch_platform.py rewrites ResolvePermissionMiddleware in the
pinned staff-api image so permissions are resolved per application
(`get_application_permissions_for_user?application_mnemonic=<client_id>`)
instead of by bare role name (`get_permissions_for_roles`, which answers with
the first same-named role of ANY registered application -- the staging 403s
of 2026-09-21). The image build fails if the patch stops matching; this test
catches that before a build, and checks the patched middleware's behaviour
with a stubbed IAM so a rewrite of the patch cannot quietly reintroduce the
cross-application lookup.

Only stdlib + pytest: the platform's dependencies are stubbed in sys.modules
just long enough to import the patched module.
"""

import asyncio
import enum
import importlib.util
import pathlib
import runpy
import shutil
import sys
import types
import typing

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
PATCH_SCRIPT = REPO / "docker" / "patches" / "patch_platform.py"
FIXTURE = REPO / "test" / "fixtures" / "iam_core_resolve_permissions.py"
RELATIVE = pathlib.Path("iam_core/user_auth/middleware/resolve_permissions.py")

CLIENT_ID = "farmer-registry-staff-portal"


@pytest.fixture
def patched_source(tmp_path, monkeypatch, capsys):
    """Copy the pinned middleware into a fake site-packages and run the patcher on it."""
    target = tmp_path / RELATIVE
    target.parent.mkdir(parents=True)
    shutil.copyfile(FIXTURE, target)

    monkeypatch.setenv("PATCH_PLATFORM_SITE_PACKAGES", str(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(PATCH_SCRIPT), run_name="__main__")
    out = capsys.readouterr()
    assert exit_info.value.code == 0, out.err
    assert "applied to resolve_permissions.py" in out.out
    return target.read_text()


def test_patch_applies_and_compiles(patched_source):
    compile(patched_source, "resolve_permissions.py", "exec")
    assert "/user-access/get_permissions_for_roles" not in patched_source
    assert "/user-access/get_application_permissions_for_user" in patched_source
    assert (
        "_fetch_permissions_for_roles(\n                user_roles, principal, client_id"
        in patched_source
    )


def test_patch_is_idempotent(patched_source, tmp_path, monkeypatch, capsys):
    """A second run must report 'already applied', not fail on a missing match."""
    monkeypatch.setenv("PATCH_PLATFORM_SITE_PACKAGES", str(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(PATCH_SCRIPT), run_name="__main__")
    assert exit_info.value.code == 0, capsys.readouterr().err
    assert (tmp_path / RELATIVE).read_text() == patched_source


# --- behaviour of the patched middleware against a stubbed IAM ---------------


class _ForbiddenError(Exception):
    def __init__(self, message="Forbidden"):
        super().__init__(message)
        self.message = message


class _UnauthorizedError(Exception):
    pass


class _HTTPError(Exception):
    pass


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise _HTTPError(self.status)

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Records the request and answers with whatever the test queued."""

    calls: typing.ClassVar[list] = []
    reply: typing.ClassVar[_Response] = _Response([])

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        _FakeAsyncClient.calls.append(
            {"url": url, "params": params, "headers": headers}
        )
        return _FakeAsyncClient.reply

    async def post(self, *args, **kwargs):
        raise AssertionError("patched middleware must not POST to IAM")


class _Principal:
    def __init__(self, credentials):
        self.credentials = credentials
        self.client_roles = {CLIENT_ID: ["Operations Administrator"]}


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


@pytest.fixture
def middleware(patched_source, tmp_path, monkeypatch):
    """Import the patched module with the platform's imports replaced by stubs."""
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.reply = _Response([])

    class _Settings:
        auth_provider_api_url = "http://iam"

        @classmethod
        def get_config(cls, strict=True):
            return cls()

    class _BaseHTTPMiddleware:
        def __init__(self, app):
            self.app = app

    monkeypatch.setitem(
        sys.modules,
        "httpx",
        _stub("httpx", AsyncClient=_FakeAsyncClient, HTTPError=_HTTPError),
    )
    monkeypatch.setitem(sys.modules, "fastapi", _stub("fastapi", Request=object))
    monkeypatch.setitem(sys.modules, "starlette", _stub("starlette"))
    monkeypatch.setitem(
        sys.modules, "starlette.middleware", _stub("starlette.middleware")
    )
    monkeypatch.setitem(
        sys.modules,
        "starlette.middleware.base",
        _stub("starlette.middleware.base", BaseHTTPMiddleware=_BaseHTTPMiddleware),
    )
    monkeypatch.setitem(
        sys.modules, "openg2p_fastapi_common", _stub("openg2p_fastapi_common")
    )
    monkeypatch.setitem(
        sys.modules,
        "openg2p_fastapi_common.errors",
        _stub("openg2p_fastapi_common.errors"),
    )
    monkeypatch.setitem(
        sys.modules,
        "openg2p_fastapi_common.errors.base_exception",
        _stub(
            "openg2p_fastapi_common.errors.base_exception", BaseAppException=Exception
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "openg2p_fastapi_common.errors.http_exceptions",
        _stub(
            "openg2p_fastapi_common.errors.http_exceptions",
            ForbiddenError=_ForbiddenError,
            UnauthorizedError=_UnauthorizedError,
        ),
    )
    pkg = _stub("iam_core")
    pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "iam_core", pkg)
    monkeypatch.setitem(
        sys.modules,
        "iam_core.schemas",
        _stub("iam_core.schemas", AuthPrincipal=_Principal),
    )
    user_auth = _stub("iam_core.user_auth")
    user_auth.__path__ = []
    monkeypatch.setitem(sys.modules, "iam_core.user_auth", user_auth)
    monkeypatch.setitem(
        sys.modules,
        "iam_core.user_auth.config",
        _stub("iam_core.user_auth.config", Settings=_Settings),
    )
    monkeypatch.setitem(
        sys.modules,
        "iam_core.user_auth.decorators",
        _stub(
            "iam_core.user_auth.decorators",
            get_required_permissions=lambda endpoint: None,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "iam_core.user_auth.enums",
        _stub(
            "iam_core.user_auth.enums",
            RequestStateKey=enum.StrEnum(
                "RequestStateKey", {"AUTH": "auth", "PERMISSIONS": "permissions"}
            ),
        ),
    )
    helpers = _stub("iam_core.user_auth.helpers")
    helpers.__path__ = []
    monkeypatch.setitem(sys.modules, "iam_core.user_auth.helpers", helpers)
    monkeypatch.setitem(
        sys.modules,
        "iam_core.user_auth.helpers.error_response_helper",
        _stub(
            "iam_core.user_auth.helpers.error_response_helper",
            user_auth_error_response=lambda r, e: e,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "iam_core.user_auth.helpers.route_helper",
        _stub("iam_core.user_auth.helpers.route_helper", match_route=lambda r: None),
    )
    mw_pkg = _stub("iam_core.user_auth.middleware")
    mw_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "iam_core.user_auth.middleware", mw_pkg)

    name = "iam_core.user_auth.middleware.resolve_permissions"
    spec = importlib.util.spec_from_file_location(name, tmp_path / RELATIVE)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module.ResolvePermissionMiddleware(app=None, client_id=CLIENT_ID)


def _resolve(middleware, roles, principal):
    return asyncio.run(
        middleware._fetch_permissions_for_roles(roles, principal, CLIENT_ID)
    )


def test_asks_iam_for_this_application_with_the_callers_token(middleware):
    _FakeAsyncClient.reply = _Response(
        [
            {
                "application_id": 1,
                "application_mnemonic": "registry-staff-portal",
                "permissions": ["intakeForm:view"],
            },
            {
                "application_id": 4,
                "application_mnemonic": CLIENT_ID,
                "permissions": ["intakeFormDefinition:view", "intakeSubmission:view"],
            },
        ]
    )

    permissions = _resolve(
        middleware, ["Operations Administrator"], _Principal("tok-123")
    )

    assert permissions == {"intakeFormDefinition:view", "intakeSubmission:view"}
    (call,) = _FakeAsyncClient.calls
    assert call["url"] == "http://iam/user-access/get_application_permissions_for_user"
    assert call["params"] == {"application_mnemonic": CLIENT_ID}
    assert call["headers"] == {"Authorization": "Bearer tok-123"}


def test_no_roles_means_no_permissions_and_no_call(middleware):
    assert _resolve(middleware, [], _Principal("tok-123")) == set()
    assert _FakeAsyncClient.calls == []


def test_iam_failure_is_forbidden_not_a_crash(middleware):
    _FakeAsyncClient.reply = _Response(None, status=502)
    with pytest.raises(_ForbiddenError, match="Unable to fetch user permissions"):
        _resolve(middleware, ["Operations Administrator"], _Principal("tok-123"))


def test_missing_token_is_forbidden(middleware):
    with pytest.raises(_ForbiddenError):
        _resolve(middleware, ["Operations Administrator"], _Principal(""))
    assert _FakeAsyncClient.calls == []
