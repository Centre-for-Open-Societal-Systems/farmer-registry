"""Detached JWS over the envelope's message payload, as the registry partner API verifies it."""

import json
import os
from typing import Any

from jwt.api_jws import PyJWS

KEY_ENV = "CONNECTOR_REGISTRY_SIGNATURE_KEY_PEM"
KEY_ID_ENV = "CONNECTOR_REGISTRY_SIGNATURE_KEY_ID"
ALGORITHM_ENV = "CONNECTOR_REGISTRY_SIGNATURE_ALGORITHM"
ALGORITHMS = ("EdDSA", "ES256", "RS256")


def canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sign_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    key = os.environ.get(KEY_ENV, "")
    key_id = os.environ.get(KEY_ID_ENV, "").strip()
    algorithm = os.environ.get(ALGORITHM_ENV, "EdDSA").strip()
    if not key.strip() or not key_id:
        raise ValueError(f"Registry signature is not configured ({KEY_ENV}, {KEY_ID_ENV})")
    if algorithm not in ALGORITHMS:
        raise ValueError(f"{ALGORITHM_ENV} must be one of {', '.join(ALGORITHMS)}")
    try:
        token = PyJWS().encode(canonical_payload(envelope["message"]["payload"]), key,
                               algorithm=algorithm, headers={"kid": key_id})
    except Exception:
        raise ValueError("Registry signature failed") from None
    protected, _, signature = token.split(".")
    envelope["header"].update(signature=f"{protected}..{signature}", signature_algorithm=algorithm)
    return envelope
