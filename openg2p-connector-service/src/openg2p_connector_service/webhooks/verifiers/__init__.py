"""Pluggable webhook signature verifiers.

Each verifier is a callable ``(secret, body, headers) -> None`` that raises
``HTTPException`` on failure.
"""

from typing import Callable

from fastapi import HTTPException

verifier_registry: dict[str, Callable[..., None]] = {}


def _register(name: str):
    def decorator(fn: Callable[..., None]):
        verifier_registry[name] = fn
        return fn
    return decorator


from .hmac_sha256 import verify_hmac_sha256  # noqa: E402
from .plain_shared_token import verify_plain_shared_token  # noqa: E402

verifier_registry["none"] = lambda secret, body, headers: None


def verify_webhook(
    verifier_name: str, secret: str, body: bytes, headers: dict[str, str]
) -> None:
    """Dispatch to the named verifier.

    No-op when secret is empty OR verifier_name is 'none'. Use
    ``webhook_verifier=none`` for hubs that send a ``hub.secret`` on
    subscribe but do not include ``X-Hub-Signature-256`` on delivery
    (e.g. MOSIP KafkaHub).
    """
    if not secret or verifier_name == "none":
        return
    fn = verifier_registry.get(verifier_name)
    if fn is None:
        raise HTTPException(
            500, f"Unknown webhook_verifier: {verifier_name!r}"
        )
    fn(secret, body, headers)
