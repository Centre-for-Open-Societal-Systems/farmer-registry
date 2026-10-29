"""Detached JWS over the envelope's message payload, as the registry partner API verifies it.

The key belongs to the connector's sender partner (g2p_sender_id), so it is read from the
connector's write-only auth secrets, ``auth_secret_json.registry_signature``:
``{"key_pem": ..., "key_id": ..., "algorithm": "EdDSA"}``. The connector API never returns
auth secrets, and the published chart sets no extra environment. The environment
variables below are the fallback for deployments that can set them.
"""

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


def signing_key(connector) -> tuple[str, str, str]:
    stored = (connector.get_auth_secrets() or {}).get("registry_signature") or {}
    key = stored.get("key_pem") or os.environ.get(KEY_ENV, "")
    key_id = (stored.get("key_id") or os.environ.get(KEY_ID_ENV, "")).strip()
    algorithm = (stored.get("algorithm") or os.environ.get(ALGORITHM_ENV, "") or "EdDSA").strip()
    if not key.strip() or not key_id:
        raise ValueError("Registry signature is not configured (auth_secret_json.registry_signature)")
    if algorithm not in ALGORITHMS:
        raise ValueError(f"Registry signature algorithm must be one of {', '.join(ALGORITHMS)}")
    return key, key_id, algorithm


def sign_envelope(connector, envelope: dict[str, Any]) -> dict[str, Any]:
    key, key_id, algorithm = signing_key(connector)
    try:
        token = PyJWS().encode(canonical_payload(envelope["message"]["payload"]), key,
                               algorithm=algorithm, headers={"kid": key_id})
    except Exception:
        raise ValueError("Registry signature failed") from None
    protected, _, signature = token.split(".")
    envelope["header"].update(signature=f"{protected}..{signature}", signature_algorithm=algorithm)
    return envelope
