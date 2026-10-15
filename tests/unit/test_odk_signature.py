"""Real RSA signatures with a mocked PM HTTP boundary, no secrets or live data."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("odk_signature", ROOT / "farmer-extension/src/openg2p_registry_farmer_extension/odk_signature.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class Rejected(Exception):
    def __init__(self, **kwargs): super().__init__(kwargs["detail"])


@pytest.mark.parametrize("fault", [None, "tamper", "message-id", "issuer", "expired", "wrong-key", "missing", "algorithm", "kid", "inactive", "pm-unavailable", "long-lifetime", "key-partner"])
def test_signature_binding_and_fail_closed(monkeypatch, fault):
    monkeypatch.setitem(sys.modules, "fastapi", SimpleNamespace(HTTPException=Rejected))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    message = {"payload": {"name": "Synthetic", "photo": {"data": "fixture"}}}
    now = int(time.time())
    claims = {"iss": "farmer-partner", "iat": now, "exp": now + 300, "message_id": "synthetic",
              "body_sha256": hashlib.sha256(json.dumps(message, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    header = {"sender_id": "farmer-partner", "message_id": "synthetic", "signature_algorithm": "RS256"}
    key_doc = {"partner_id": "farmer-partner", "kid": "test-key", "algorithm": "RS256", "public_key": public}
    if fault == "issuer": claims["iss"] = "other-partner"
    if fault == "expired": claims.update(iat=now-600, exp=now-300)
    if fault == "long-lifetime": claims["exp"] = now+3600
    if fault == "message-id": header["message_id"] = "other-id"
    if fault == "algorithm": header["signature_algorithm"] = "none"
    if fault == "key-partner": key_doc["partner_id"] = "other-partner"
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048) if fault == "wrong-key" else key
    signature = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "other-key" if fault == "kid" else "test-key"})
    if fault == "missing": signature = "stub-sig"
    if fault == "tamper": message["payload"]["name"] = "Changed"
    actual_client = httpx.AsyncClient
    def response(request):
        assert request.url.host == "pm.internal"
        return httpx.Response(404 if fault == "inactive" else 503 if fault == "pm-unavailable" else 200, json=key_doc)
    monkeypatch.setattr(verifier.httpx, "AsyncClient", lambda **kw: actual_client(transport=httpx.MockTransport(response), **kw))
    call = verifier.verify_odk_signature("farmer-partner", signature, message, {"body": {"header": header}}, "http://pm.internal")
    if fault:
        with pytest.raises(Rejected, match="Invalid Farmer ODK message signature"): asyncio.run(call)
    else: asyncio.run(call)


def test_build_patch_rejects_drift_and_reruns(tmp_path):
    spec = importlib.util.spec_from_file_location("signature_patch", ROOT / "docker/partner-api/patch_odk_signature.py")
    patcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(patcher)
    path = tmp_path / "service.py"
    path.write_text("class Service:\n    async def method(self):\n        if True:\n" + patcher.DEDUPE_OLD + patcher.OLD)
    patcher.patch(path); patcher.patch(path)
    assert "await verify_odk_signature(" in path.read_text()
    path.write_text("changed_platform = True\n")
    with pytest.raises(RuntimeError): patcher.patch(path)
