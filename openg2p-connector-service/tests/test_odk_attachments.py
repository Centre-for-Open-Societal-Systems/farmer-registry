"""ODK attachments travel inline when ``embed_attachments`` is set.

OData gives an attachment's file name only (a land certificate photo, say);
the bytes are a separate Central download. With the option on, the transport
lists each submission's attachments, downloads them and replaces the name,
wherever it appears, with the {"__type": "File", ...} value the registry's
file fields accept.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx
import pytest

from openg2p_connector_service.auth.base import AuthContext
from openg2p_connector_service.config import get_settings
from openg2p_connector_service.transports import get_transport


class FakeConnector:
    def __init__(self, source_config: dict[str, Any]):
        self.connector_id = "conn-test"
        self.auth_type = "odk_session"
        self._source = source_config

    def get_source_config(self) -> dict[str, Any]:
        return dict(self._source)

    def get_poll_state(self) -> dict[str, Any]:
        return {}


class _FakeAuth:
    async def get_auth_context(self, _connector):
        return AuthContext(headers={}, base_url=None)


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch):
    monkeypatch.setattr(
        "openg2p_connector_service.transports.odk_central.get_auth_strategy",
        lambda _name: _FakeAuth(),
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "strict_incremental", False, raising=False)


SUBMISSION = {
    "__id": "uuid:abc",
    "__system": {"submissionDate": "2026-10-07T05:10:00.000Z"},
    "land_info": {
        "land_info_repeat": [
            {"land_id": "02", "land_certificate": "deed.jpg"},
            {"land_id": "03", "land_certificate": "missing.jpg"},
        ]
    },
}
JPEG = b"\xff\xd8\xff\xe0certificate-bytes"


def _routes(responses: dict[str, httpx.Response]):
    calls: list[str] = []

    async def _fake_get(self, url, *, headers=None, params=None):
        calls.append(url)
        for suffix, response in responses.items():
            if url.endswith(suffix):
                return response
        raise AssertionError(f"Unexpected ODK request {url}")

    return calls, _fake_get


def _json(body, status=200):
    return httpx.Response(status, json=body, request=httpx.Request("GET", "http://odk.test"))


def _bytes(content, content_type="image/jpeg"):
    return httpx.Response(200, content=content, headers={"content-type": content_type},
                          request=httpx.Request("GET", "http://odk.test"))


async def _fetch(monkeypatch, source_config, responses):
    calls, fake_get = _routes(responses)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    transport = get_transport("odk_central")
    records = [r async for r in transport.fetch(FakeConnector(source_config))]
    return records, calls


CONFIG = {"base_url": "http://odk.test", "project_id": 13, "form_id": "farmer_profile",
          "max_pages": 1, "embed_attachments": True}


@pytest.mark.asyncio
async def test_attachment_is_inlined_where_its_name_appears(monkeypatch):
    import copy

    records, calls = await _fetch(monkeypatch, CONFIG, {
        "/Submissions": _json({"value": [copy.deepcopy(SUBMISSION)]}),
        "/submissions/uuid%3Aabc/attachments": _json([
            {"name": "deed.jpg", "exists": True},
            {"name": "missing.jpg", "exists": False},
        ]),
        "/attachments/deed.jpg": _bytes(JPEG),
    })

    lands = records[0].data["land_info"]["land_info_repeat"]
    assert lands[0]["land_certificate"] == {
        "__type": "File",
        "name": "deed.jpg",
        "type": "image/jpeg",
        "data": base64.b64encode(JPEG).decode("ascii"),
    }
    # Not uploaded to Central: the name stays and nothing is downloaded for it.
    assert lands[1]["land_certificate"] == "missing.jpg"
    assert not any(url.endswith("/attachments/missing.jpg") for url in calls)


@pytest.mark.asyncio
async def test_oversized_attachment_is_left_as_its_name(monkeypatch):
    import copy

    records, _ = await _fetch(monkeypatch, {**CONFIG, "attachment_max_bytes": 4}, {
        "/Submissions": _json({"value": [copy.deepcopy(SUBMISSION)]}),
        "/submissions/uuid%3Aabc/attachments": _json([{"name": "deed.jpg", "exists": True}]),
        "/attachments/deed.jpg": _bytes(JPEG),
    })

    assert records[0].data["land_info"]["land_info_repeat"][0]["land_certificate"] == "deed.jpg"


@pytest.mark.asyncio
async def test_attachments_are_not_fetched_unless_enabled(monkeypatch):
    import copy

    records, calls = await _fetch(monkeypatch, {**CONFIG, "embed_attachments": False}, {
        "/Submissions": _json({"value": [copy.deepcopy(SUBMISSION)]}),
    })

    assert records[0].data["land_info"]["land_info_repeat"][0]["land_certificate"] == "deed.jpg"
    assert all("/attachments" not in url for url in calls)


@pytest.mark.asyncio
async def test_attachments_are_embedded_by_default(monkeypatch):
    import copy

    # Pipelines created before the option existed carry no embed_attachments key.
    config = {k: v for k, v in CONFIG.items() if k != "embed_attachments"}
    records, _ = await _fetch(monkeypatch, config, {
        "/Submissions": _json({"value": [copy.deepcopy(SUBMISSION)]}),
        "/submissions/uuid%3Aabc/attachments": _json([{"name": "deed.jpg", "exists": True}]),
        "/attachments/deed.jpg": _bytes(JPEG),
    })

    cert = records[0].data["land_info"]["land_info_repeat"][0]["land_certificate"]
    assert cert["__type"] == "File" and cert["name"] == "deed.jpg"
