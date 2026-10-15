"""Verify Farmer ODK envelopes against active Partner Management public keys."""
import hashlib
import hmac
import json
from urllib.parse import quote

import httpx
import jwt


async def verify_odk_signature(partner_id, signature, message, envelope, key_api_url):
    """Reject unbound, expired, tampered, unsigned or inactive-partner messages.

    The caller has already required an active PM partner. The key-fetch API also
    serves only active partners' currently valid keys. No token-provided URL is
    used for key discovery and JWT algorithms are restricted to RS256.
    """
    try:
        header = envelope["body"]["header"]
        if (not key_api_url or header.get("sender_id") != partner_id
                or header.get("signature_algorithm") != "RS256"):
            raise ValueError("invalid envelope")
        protected = jwt.get_unverified_header(signature)
        kid = protected.get("kid")
        if protected.get("alg") != "RS256" or not isinstance(kid, str) or not kid:
            raise ValueError("invalid key id")
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get(key_api_url.rstrip("/") + "/keys/" + quote(partner_id, safe="") + "/" + quote(kid, safe=""))
            response.raise_for_status()
            key = response.json()
        if key.get("partner_id") != partner_id or key.get("kid") != kid or key.get("algorithm") != "RS256":
            raise ValueError("invalid partner key")
        claims = jwt.decode(signature, key["public_key"], algorithms=["RS256"], issuer=partner_id,
                            options={"require": ["iss", "iat", "exp", "message_id", "body_sha256"]})
        expected = hashlib.sha256(json.dumps(message, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        if (claims["message_id"] != header["message_id"]
                or not isinstance(claims["body_sha256"], str)
                or not hmac.compare_digest(claims["body_sha256"], expected)
                or claims["exp"] - claims["iat"] > 300):
            raise ValueError("message binding failed")
    except Exception:
        # Never include key material, signatures or private message data.
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid Farmer ODK message signature") from None
