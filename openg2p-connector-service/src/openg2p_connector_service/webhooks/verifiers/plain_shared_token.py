import hmac

from fastapi import HTTPException

from . import verifier_registry


def verify_plain_shared_token(
    secret: str, body: bytes, headers: dict[str, str]
) -> None:
    """Verify a simple shared token passed in the Authorization or X-Webhook-Token header."""
    token = (
        headers.get("x-webhook-token")
        or headers.get("X-Webhook-Token")
        or headers.get("authorization")
        or headers.get("Authorization")
        or ""
    )
    token = token.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(secret, token):
        raise HTTPException(403, "Invalid shared token")


verifier_registry["plain_shared_token"] = verify_plain_shared_token
