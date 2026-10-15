"""Run inside the built connector image, with its real upstream package."""
import base64
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from coss_connector.odk_media import AttachmentTransferError, FarmerOdkTransport, embed
from openg2p_connector_service.models import ConnectorDefinition
from openg2p_connector_service.transports.base import SourceRecord
from openg2p_connector_service.transports.checkpoints import Checkpoint, CheckpointMode
from openg2p_connector_service.transports.odk_central import OdkCentralTransport
from openg2p_connector_service.transports.registry import get_transport


class MediaTests(unittest.IsolatedAsyncioTestCase):
    async def test_nested_attachments_preserve_source_identity(self):
        entry = {"__id": "uuid:synthetic", "photo": "photo.jpg", "land": [{"certificate": "land.pdf"}]}
        def handle(request):
            if request.url.path.endswith('/attachments'):
                return httpx.Response(200, json=[{"name": "photo.jpg", "exists": True}, {"name": "land.pdf", "exists": True}])
            return httpx.Response(200, content=b"synthetic-bytes", headers={"content-type": "application/pdf"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            await embed(client, "https://odk.example/attachments", {}, entry, 100)
        self.assertEqual(entry["__id"], "uuid:synthetic")
        self.assertEqual(entry["photo"]["data"], base64.b64encode(b"synthetic-bytes").decode())
        self.assertEqual(entry["land"][0]["certificate"]["__type"], "File")

    async def test_missing_attachment_is_not_sent_as_a_filename(self):
        def handle(request):
            return httpx.Response(200, json=[{"name": "photo.jpg", "exists": False}])
        entry = {"photo": "photo.jpg"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with self.assertRaises(AttachmentTransferError):
                await embed(client, "https://odk.example/attachments", {}, entry, 100)
        self.assertEqual(entry, {"photo": "photo.jpg"})

    async def test_streaming_limit_cannot_be_bypassed_by_absent_length_header(self):
        def handle(request):
            if request.url.path.endswith('/attachments'):
                return httpx.Response(200, json=[{"name": "photo.jpg"}])
            response = httpx.Response(200, content=b"too-many-bytes")
            del response.headers["content-length"]
            return response
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with self.assertRaises(AttachmentTransferError):
                await embed(client, "https://odk.example/attachments", {}, {"photo": "photo.jpg"}, 4)

    async def test_transport_retains_upstream_checkpoint_and_duplicate_key(self):
        checkpoint = Checkpoint(mode=CheckpointMode.TIMESTAMP, value="2026-10-15T00:00:00Z", boundary_ids=["uuid:synthetic"])
        record = SourceRecord("farmer:uuid:synthetic", {"__id": "uuid:synthetic", "photo": "photo.jpg"}, checkpoint=checkpoint)
        async def fetch(_self, _connector):
            yield record
        def handle(request):
            if request.url.path.endswith('/attachments'):
                return httpx.Response(200, json=[{"name": "photo.jpg"}])
            return httpx.Response(200, content=b"image")
        actual_client = httpx.AsyncClient
        connector = ConnectorDefinition(auth_type="none", source_config_json=json.dumps({"base_url": "https://odk.example", "project_id": 1, "form_id": "farmer"}))
        auth = SimpleNamespace(get_auth_context=AsyncMock(return_value=SimpleNamespace(headers={}, base_url=None)))
        with patch.object(OdkCentralTransport, "fetch", fetch), patch("coss_connector.odk_media.get_auth_strategy", return_value=auth), patch("coss_connector.odk_media.httpx.AsyncClient", side_effect=lambda **kw: actual_client(transport=httpx.MockTransport(handle), **kw)):
            result = [item async for item in FarmerOdkTransport().fetch(connector)]
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].checkpoint, checkpoint)
        self.assertEqual(result[0].source_event_id, "farmer:uuid:synthetic")
        self.assertEqual(result[0].data["photo"]["__type"], "File")

    async def test_no_record_is_yielded_after_attachment_failure(self):
        record = SourceRecord("farmer:uuid:synthetic", {"__id": "uuid:synthetic", "photo": "photo.jpg"})
        async def fetch(_self, _connector):
            yield record
        actual_client = httpx.AsyncClient
        connector = ConnectorDefinition(auth_type="none", source_config_json=json.dumps({"base_url": "https://odk.example", "project_id": 1, "form_id": "farmer"}))
        auth = SimpleNamespace(get_auth_context=AsyncMock(return_value=SimpleNamespace(headers={}, base_url=None)))
        with patch.object(OdkCentralTransport, "fetch", fetch), patch("coss_connector.odk_media.get_auth_strategy", return_value=auth), patch("coss_connector.odk_media.httpx.AsyncClient", side_effect=lambda **kw: actual_client(transport=httpx.MockTransport(lambda req: httpx.Response(503)), **kw)):
            with self.assertRaises(httpx.HTTPStatusError):
                _ = [item async for item in FarmerOdkTransport().fetch(connector)]

    async def test_missing_draft_file_never_falls_back_to_other_submission_bytes(self):
        record = SourceRecord("farmer:uuid:synthetic", {"__id": "uuid:synthetic", "photo": "photo.jpg"})
        async def fetch(_self, _connector):
            yield record
        requested = []
        def handle(request):
            requested.append(request.url.path)
            if request.url.path.endswith('/attachments'):
                return httpx.Response(200, json=[{"name": "photo.jpg"}])
            return httpx.Response(404)
        actual_client = httpx.AsyncClient
        connector = ConnectorDefinition(auth_type="none", source_config_json=json.dumps({"base_url": "https://odk.example", "project_id": 1, "form_id": "farmer", "use_draft": True}))
        auth = SimpleNamespace(get_auth_context=AsyncMock(return_value=SimpleNamespace(headers={}, base_url=None)))
        with patch.object(OdkCentralTransport, "fetch", fetch), patch("coss_connector.odk_media.get_auth_strategy", return_value=auth), patch("coss_connector.odk_media.httpx.AsyncClient", side_effect=lambda **kw: actual_client(transport=httpx.MockTransport(handle), **kw)):
            with self.assertRaises(httpx.HTTPStatusError):
                _ = [item async for item in FarmerOdkTransport().fetch(connector)]
        self.assertTrue(all('/draft/' in path for path in requested))

    def test_adapter_is_registered_without_replacing_upstream_checkpoint_engine(self):
        self.assertIsInstance(get_transport("odk_central"), FarmerOdkTransport)
        self.assertTrue(issubclass(FarmerOdkTransport, OdkCentralTransport))

    def test_replacement_worker_and_dispatch_do_not_consume_old_celery_queue(self):
        from coss_connector.celery_config import configure
        from openg2p_connector_service.worker import celery_app
        configure(celery_app)
        route = celery_app.amqp.router.route({}, 'connector.poll', args=('synthetic',), kwargs={})
        self.assertEqual(route['queue'].name, 'farmer-registry-connector-v2')
        self.assertNotEqual(route['queue'].name, 'celery')


if __name__ == "__main__":
    unittest.main()
