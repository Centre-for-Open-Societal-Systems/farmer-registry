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
from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_farmer_extension import odk_signature


class SignatureRuntime(unittest.IsolatedAsyncioTestCase):
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
            with self.assertRaises(G2PRegistryException):
                await service._match_model_signature_pattern("FARMER_ODK_MODEL", envelope, session)
            # Unrelated models retain their existing integration contracts.
            await service._match_model_signature_pattern("OTHER_MODEL", envelope, session)


if __name__ == "__main__": unittest.main()
