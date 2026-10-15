"""Background intake must authenticate to AWE and fail closed on token errors."""
import importlib.util
from pathlib import Path
import asyncio
import functools
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


token = load("awe_worker_token", "farmer-extension/src/openg2p_registry_farmer_extension/awe_worker_token.py")
patcher = load("patch_awe_worker", "docker/celery/assets/patch_awe_worker.py")


def async_test(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))
    return wrapped


@pytest.fixture(autouse=True)
def config(monkeypatch):
    token._cache.clear()
    for name, value in {"ENABLED": "true", "TOKEN_URL": "https://keycloak.example/realms/staff/protocol/openid-connect/token",
                        "CLIENT_ID": "farmer-worker", "CLIENT_SECRET": "private-fixture"}.items():
        monkeypatch.setenv(token.PREFIX + name, value)


def client(monkeypatch, response):
    send = AsyncMock(return_value=response)
    fake = AsyncMock()
    fake.__aenter__.return_value.post = send
    monkeypatch.setattr(token.httpx, "AsyncClient", lambda **kw: fake)
    return send


@async_test
async def test_token_is_acquired_cached_and_refreshed(monkeypatch):
    clock = [100]
    monkeypatch.setattr(token.time, "monotonic", lambda: clock[0])
    response = httpx.Response(200, json={"access_token": "synthetic-token", "expires_in": 60}, request=httpx.Request("POST", "https://keycloak.example"))
    send = client(monkeypatch, response)
    assert await token.service_token() == "synthetic-token"
    assert await token.service_token() == "synthetic-token"
    assert send.await_count == 1
    assert send.call_args.kwargs["data"]["grant_type"] == "client_credentials"
    clock[0] += 31
    await token.service_token()
    assert send.await_count == 2


@async_test
async def test_disabled_awe_does_not_request_a_token(monkeypatch):
    monkeypatch.setenv(token.PREFIX + "ENABLED", "false")
    monkeypatch.setattr(token.httpx, "AsyncClient", lambda **kw: pytest.fail("AWE disabled"))
    assert await token.service_token() is None


@async_test
async def test_missing_credentials_fail_before_request(monkeypatch):
    monkeypatch.delenv(token.PREFIX + "CLIENT_SECRET")
    with pytest.raises(RuntimeError, match="credentials are incomplete"):
        await token.service_token()


@async_test
@pytest.mark.parametrize("status,body", [(401, {"error": "private-fixture"}), (200, {}),
                                        (200, {"access_token": "", "expires_in": 60})])
async def test_token_failures_are_not_cached_or_logged(monkeypatch, status, body):
    client(monkeypatch, httpx.Response(status, json=body, request=httpx.Request("POST", "https://keycloak.example")))
    with pytest.raises(RuntimeError, match="token acquisition failed") as error:
        await token.service_token()
    assert "private-fixture" not in str(error.value)
    assert not token._cache


def test_worker_patch_passes_the_acquired_token_and_rejects_platform_drift(tmp_path):
    source = tmp_path / "worker.py"
    source.write_text(patcher.OLD)
    patcher.patch(source)
    assert "bearer_token=await service_token()" in source.read_text()
    patcher.patch(source)
    source.write_text("async def changed(): pass\n")
    with pytest.raises(RuntimeError, match="Platform finalizer changed"):
        patcher.patch(source)


@async_test
async def test_real_finalizer_passes_token_before_starting_workflow(monkeypatch):
    acquire = AsyncMock(return_value="synthetic-worker-token")
    finalize = AsyncMock()
    monkeypatch.setitem(sys.modules, "openg2p_registry_farmer_extension.awe_worker_token",
                        SimpleNamespace(service_token=acquire))
    scope = {"G2PIntakeFormDataService": SimpleNamespace(get_component=lambda: SimpleNamespace(finalize_submission_with_session=finalize))}
    exec(patcher.NEW, scope)
    session = object()
    await scope["_finalize_submission_async"]("synthetic-submission", session)
    finalize.assert_awaited_once_with("synthetic-submission", session, bearer_token="synthetic-worker-token")
    finalize.reset_mock()
    acquire.side_effect = RuntimeError("AWE worker token acquisition failed")
    with pytest.raises(RuntimeError, match="token acquisition failed"):
        await scope["_finalize_submission_async"]("synthetic-submission", session)
    finalize.assert_not_awaited()
