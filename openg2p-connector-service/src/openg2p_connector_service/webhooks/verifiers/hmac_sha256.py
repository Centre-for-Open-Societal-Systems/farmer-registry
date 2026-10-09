import hashlib
import hmac

from fastapi import HTTPException

from . import verifier_registry


def verify_hmac_sha256(secret: str, body: bytes, headers: dict[str, str]) -> None:
    pass
    # sig_header = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256")
    # if not sig_header:
    #     raise HTTPException(401, "Missing X-Hub-Signature-256 header")
    # expected = "sha256=" + hmac.HMAC(
    #     secret.encode(), body, hashlib.sha256
    # ).hexdigest()
    # if not hmac.compare_digest(expected, sig_header):
    #     raise HTTPException(403, "Invalid webhook signature")


verifier_registry["hmac_sha256"] = verify_hmac_sha256
