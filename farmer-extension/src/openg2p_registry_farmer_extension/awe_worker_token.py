"""Client credentials for background intake finalization; no user impersonation."""
import os
import time

import httpx

_cache = {}
PREFIX = "REGISTRY_CELERY_WORKERS_AWE_"


async def service_token():
    if os.environ.get(PREFIX + "ENABLED", "false").lower() not in ("true", "1", "yes"):
        return None
    url, client_id, secret = (os.environ.get(PREFIX + name, "").strip()
                              for name in ("TOKEN_URL", "CLIENT_ID", "CLIENT_SECRET"))
    if not all((url, client_id, secret)):
        raise RuntimeError("AWE worker client credentials are incomplete")
    key = (url, client_id, secret)
    cached = _cache.get(key)
    if cached and cached[1] > time.monotonic() + 30:
        return cached[0]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, data={"grant_type": "client_credentials",
                                                   "client_id": client_id, "client_secret": secret})
            response.raise_for_status()
            body = response.json()
        token = body["access_token"]
        lifetime = float(body.get("expires_in", 60))
        if not isinstance(token, str) or not token or lifetime <= 0:
            raise ValueError("Invalid token response")
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        # Responses/exceptions can include credentials; emit only a fixed reason.
        raise RuntimeError("AWE worker token acquisition failed") from None
    _cache.clear()
    _cache[key] = (token, time.monotonic() + lifetime)
    return token
