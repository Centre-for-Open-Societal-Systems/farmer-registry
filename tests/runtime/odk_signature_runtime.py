"""Exercise the patched Partner API service with its actual installed classes."""
import hashlib
import json
import sys
import time
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

sys.modules["openg2p_registry_extensions"] = importlib.import_module("openg2p_registry_farmer_extension")
from openg2p_registry_core.services.g2p_ingest_service import G2PIngestService
from openg2p_registry_core.helpers import PatternMatcher
from fastapi import HTTPException
from openg2p_registry_farmer_extension import odk_signature


class SignatureRuntime(unittest.IsolatedAsyncioTestCase):
    async def test_controller_preserves_signature_authentication_status(self):
        from openg2p_registry_partner_api.ingestion.controllers.g2p_ingest_controller import G2PIngestController
        controller = object.__new__(G2PIngestController)
        controller.request_response_helper = SimpleNamespace(construct_http_request=AsyncMock(return_value={}))
        controller.g2p_ingest_controller_service = SimpleNamespace(ingest_data=AsyncMock(side_effect=HTTPException(401, "Invalid Farmer ODK message signature")))
        with self.assertRaises(HTTPException) as caught:
            await controller.ingest_data(object(), "FARMER_ODK_MODEL")
        self.assertEqual(caught.exception.status_code, 401)

    async def test_retry_returns_existing_correlation_without_duplicate_intake(self):
        envelope = {"body": {"message": {"payload": {"name": "Synthetic"}}}}
        existing = SimpleNamespace(ingest_id="existing", ingest_correlation_id="original-correlation")
        session = AsyncMock()
        session.__aenter__.return_value = session
        session.execute.side_effect = [None, SimpleNamespace(scalar_one_or_none=lambda: existing)]
        stored = SimpleNamespace(raw_data_json=envelope)
        session.get.return_value = stored
        service = G2PIngestService()
        model = SimpleNamespace(data_model_id="FARMER_ODK_MODEL", response_template_document_id=None)
        with patch("openg2p_registry_core.services.g2p_ingest_service.get_async_session_maker", return_value=lambda: session), \
             patch.object(service, "_get_data_model", AsyncMock(return_value=model)), \
             patch.object(service, "_match_model_signature_pattern", AsyncMock(return_value=(SimpleNamespace(partner_id="farmer-partner"), "verified", {}, SimpleNamespace(is_list=False)))), \
             patch.object(service, "_match_message_id_pattern", return_value="synthetic"):
            result = await service.ingest_data("FARMER_ODK_MODEL", envelope)
        self.assertEqual(result, ("original-correlation", None))
        session.commit.assert_not_awaited()
        self.assertIn("pg_advisory_xact_lock", str(session.execute.call_args_list[0].args[0]))

    async def test_real_service_requires_registered_signature_for_odk_only(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        message = {"payload": {"name": "Synthetic"}}
        now = int(time.time())
        claims = {"iss": "farmer-partner", "iat": now, "exp": now+300, "message_id": "synthetic",
                  "body_sha256": hashlib.sha256(json.dumps(message, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
        signature = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})
        envelope = {"body": {"header": {"sender_id": "farmer-partner", "message_id": "synthetic", "signature_algorithm": "RS256"}, "message": message}}
        matcher = SimpleNamespace(get_signature_pattern_path=lambda *args: ("farmer-partner", signature, message))
        session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: object())))
        service = G2PIngestService()
        actual_client = httpx.AsyncClient
        def response(request):
            return httpx.Response(200, json={"partner_id": "farmer-partner", "kid": "test-key", "algorithm": "RS256", "public_key": public})
        with patch.object(PatternMatcher, "get_component", return_value=matcher), \
             patch.object(service, "_get_partner_from_partner_mnemonic", AsyncMock(return_value=SimpleNamespace(partner_id="farmer-partner"))), \
             patch("openg2p_registry_core.helpers.partner_management.get_partner_mgmt_settings", return_value=SimpleNamespace(partner_mgmt_api_url="http://pm.internal")), \
             patch.object(odk_signature.httpx, "AsyncClient", side_effect=lambda **kw: actual_client(transport=httpx.MockTransport(response), **kw)):
            await service._match_model_signature_pattern("FARMER_ODK_MODEL", envelope, session)
            message["payload"]["name"] = "Tampered"
            with self.assertRaises(HTTPException):
                await service._match_model_signature_pattern("FARMER_ODK_MODEL", envelope, session)
            # Unrelated models retain their existing integration contracts.
            await service._match_model_signature_pattern("OTHER_MODEL", envelope, session)


if __name__ == "__main__": unittest.main()
