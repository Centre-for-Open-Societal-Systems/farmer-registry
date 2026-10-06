import hashlib
import hmac
import json

import pytest

from tests.test_utils import connector_json


@pytest.mark.asyncio
async def test_webhook_unknown_connector(app_client):
    resp = await app_client.post("/webhook/nonexistent", json={
        "source_event_id": "evt1",
        "data": {"foo": "bar"},
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_disabled_connector(app_client):
    resp = await app_client.post("/connectors", json=connector_json(
        name="Disabled WH",
        platform="generic",
        transport_type="webhook",
        enabled=False,
    ))
    cid = resp.json()["connector_id"]

    resp = await app_client.post(f"/webhook/{cid}", json={
        "source_event_id": "evt1",
        "data": {"x": 1},
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_signature_required(app_client):
    resp = await app_client.post("/connectors", json=connector_json(
        name="Signed WH",
        platform="generic",
        transport_type="webhook",
        webhook_secret="s3cret",
    ))
    cid = resp.json()["connector_id"]

    resp = await app_client.post(f"/webhook/{cid}", json={
        "source_event_id": "evt1",
        "data": {"x": 1},
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_bad_signature(app_client):
    resp = await app_client.post("/connectors", json=connector_json(
        name="Bad Sig WH",
        platform="generic",
        transport_type="webhook",
        webhook_secret="s3cret",
    ))
    cid = resp.json()["connector_id"]

    resp = await app_client.post(
        f"/webhook/{cid}",
        json={"source_event_id": "evt1", "data": {"x": 1}},
        headers={"X-Hub-Signature-256": "sha256=wrong"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_valid_signature(app_client):
    resp = await app_client.post("/connectors", json=connector_json(
        name="Valid Sig WH",
        platform="generic",
        transport_type="webhook",
        webhook_secret="s3cret",
    ))
    cid = resp.json()["connector_id"]

    payload = json.dumps({"source_event_id": "evt-ok", "data": {"k": "v"}}).encode()
    sig = "sha256=" + hmac.HMAC(b"s3cret", payload, hashlib.sha256).hexdigest()

    resp = await app_client.post(
        f"/webhook/{cid}",
        content=payload,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") in ("SUCCESS", "queued")


@pytest.mark.asyncio
async def test_webhook_by_slug(app_client):
    resp = await app_client.post("/connectors", json=connector_json(
        name="Slug WH",
        platform="generic",
        transport_type="webhook",
        webhook_path_slug="my-test-slug",
    ))
    assert resp.status_code == 201

    resp = await app_client.post(
        "/webhook/by-slug/my-test-slug",
        json={"source_event_id": "slug-evt", "data": {"a": 1}},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_websub_uses_webhook_delivery_path(app_client):
    resp = await app_client.post("/connectors", json=connector_json(
        name="WebSub Push",
        platform="edrmc_websub",
        transport_type="websub",
        webhook_path_slug="edrmc-websub",
    ))
    assert resp.status_code == 201
    cid = resp.json()["connector_id"]

    resp = await app_client.post(
        "/webhook/by-slug/edrmc-websub",
        json={"source_event_id": "websub-evt", "data": {"a": 1}},
    )
    assert resp.status_code == 200

    poll_resp = await app_client.post(f"/connectors/{cid}/poll")
    assert poll_resp.status_code == 400


@pytest.mark.asyncio
async def test_websub_challenge_by_slug(app_client):
    resp = await app_client.post("/connectors", json=connector_json(
        name="WebSub Challenge",
        platform="edrmc_websub",
        transport_type="websub",
        webhook_path_slug="edrmc-challenge",
    ))
    assert resp.status_code == 201

    resp = await app_client.get(
        "/webhook/by-slug/edrmc-challenge",
        params={
            "hub.mode": "subscribe",
            "hub.topic": "edrmc-topic",
            "hub.challenge": "challenge-token",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "challenge-token"
    assert resp.headers["content-type"].startswith("text/plain")


@pytest.mark.asyncio
async def test_webhook_plain_shared_token_verifier(app_client):
    resp = await app_client.post("/connectors", json=connector_json(
        name="Token WH",
        platform="generic",
        transport_type="webhook",
        webhook_secret="my-token-123",
        webhook_verifier="plain_shared_token",
    ))
    cid = resp.json()["connector_id"]

    # missing token
    resp = await app_client.post(
        f"/webhook/{cid}",
        json={"data": {"x": 1}},
    )
    assert resp.status_code == 403

    # valid token
    resp = await app_client.post(
        f"/webhook/{cid}",
        json={"data": {"x": 1}},
        headers={"X-Webhook-Token": "my-token-123"},
    )
    assert resp.status_code == 200
