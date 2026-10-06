"""Tests for GET /connectors/meta and enriched ConnectorRead fields."""

import pytest

from tests.test_utils import connector_json


@pytest.mark.asyncio
async def test_meta_returns_registries(app_client):
    resp = await app_client.get("/connectors/meta")
    assert resp.status_code == 200
    body = resp.json()

    assert "transport_types" in body
    assert "auth_types" in body
    assert "webhook_verifiers" in body
    assert "transport_hints" in body

    assert "webhook" in body["transport_types"]
    assert "websub" in body["transport_types"]
    assert "odk_central" in body["transport_types"]
    assert "none" in body["auth_types"]
    assert "odk_session" in body["auth_types"]
    assert "hmac_sha256" in body["webhook_verifiers"]

    assert body["transport_hints"]["webhook"] == "webhook"
    assert body["transport_hints"]["websub"] == "webhook"
    assert body["transport_hints"]["odk_central"] == "poll"


@pytest.mark.asyncio
async def test_connector_read_includes_mapper_and_validation(app_client):
    resp = await app_client.post("/connectors", json=connector_json(
        name="Full Read Test",
        platform="test",
        transport_type="webhook",
        mapper_expression="{x: data.x}",
        validation_schema_json='{"type": "object"}',
    ))
    assert resp.status_code == 201
    body = resp.json()

    assert body["mapper_expression"] == "{x: data.x}"
    assert body["validation_schema_json"] == '{"type": "object"}'

    assert "auth_secret_json" not in body
    assert "webhook_secret" not in body

    cid = body["connector_id"]
    resp2 = await app_client.get(f"/connectors/{cid}")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["mapper_expression"] == "{x: data.x}"
    assert body2["validation_schema_json"] == '{"type": "object"}'


@pytest.mark.asyncio
async def test_meta_is_not_captured_as_connector_id(app_client):
    """Ensure /connectors/meta is routed before /{connector_id}."""
    resp = await app_client.get("/connectors/meta")
    assert resp.status_code == 200
    assert "transport_types" in resp.json()
