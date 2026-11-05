"""Sign the Registry message envelope with the Farmer partner's registered key."""
import hashlib
import json
import os
import time

import jwt

from openg2p_connector_service.config import get_settings
from openg2p_connector_service.services.ingestion_service import IngestionService


def signed_envelope(envelope):
    settings = get_settings()
    if not settings.signing_enabled:
        if os.environ.get("CONNECTOR_REQUIRE_SIGNING", "false").lower() == "true":
            raise ValueError("Farmer connector signing is required")
        return envelope
    kid = os.environ.get("CONNECTOR_SIGNING_KEY_ID", "").strip()
    sender = envelope["header"]["sender_id"]
    if (not settings.signing_private_key_pem.strip() or not kid
            or settings.signing_algorithm != "RS256" or settings.signing_issuer != sender):
        raise ValueError("Farmer connector signing configuration is incomplete")
    now = int(time.time())
    message = json.dumps(envelope["message"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    claims = {"iss": sender, "iat": now, "exp": now + 300,
              "message_id": envelope["header"]["message_id"],
              "body_sha256": hashlib.sha256(message).hexdigest()}
    envelope["header"]["signature"] = jwt.encode(
        claims, settings.signing_private_key_pem, algorithm="RS256", headers={"kid": kid})
    envelope["header"]["signature_algorithm"] = "RS256"
    return envelope


def install():
    original = IngestionService._wrap_in_g2p_envelope
    if getattr(original, "_farmer_signed", False):
        return

    def wrapper(self, *args, **kwargs):
        return signed_envelope(original(self, *args, **kwargs))

    wrapper._farmer_signed = True
    IngestionService._wrap_in_g2p_envelope = wrapper
