import pytest

from tests.test_utils import connector_json


@pytest.mark.asyncio
async def test_connector_lifecycle(app_client):
    # create
    resp = await app_client.post("/connectors", json=connector_json(
        name="Test ODK",
        platform="odk",
        transport_type="odk_central",
        data_model_mnemonic="ODK_HOUSEHOLD",
    ))
    assert resp.status_code == 201
    body = resp.json()
    cid = body["connector_id"]
    assert body["name"] == "Test ODK"
    assert body["enabled"] is True

    # list
    resp = await app_client.get("/connectors")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # get
    resp = await app_client.get(f"/connectors/{cid}")
    assert resp.status_code == 200

    # update
    resp = await app_client.patch(f"/connectors/{cid}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    # delete
    resp = await app_client.delete(f"/connectors/{cid}")
    assert resp.status_code == 204

    resp = await app_client.get(f"/connectors/{cid}")
    assert resp.status_code == 404
