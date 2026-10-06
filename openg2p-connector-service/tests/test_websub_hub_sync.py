"""WebSub hub subscription sync endpoint."""

import pytest

from tests.test_utils import connector_json


@pytest.mark.asyncio
async def test_websub_sync_rejects_non_websub_transport(app_client):
    resp = await app_client.post(
        "/connectors",
        json=connector_json(
            name="ODK only",
            platform="odk",
            transport_type="odk_central",
            source_config_json='{"base_url":"http://x","project_id":1,"form_id":"f"}',
            auth_type="odk_session",
            auth_secret_json='{"email":"a","password":"b"}',
        ),
    )
    assert resp.status_code == 201
    cid = resp.json()["connector_id"]

    resp = await app_client.post(f"/connectors/{cid}/websub/sync-subscriptions")
    assert resp.status_code == 400
    assert "websub" in resp.json()["detail"].lower()
