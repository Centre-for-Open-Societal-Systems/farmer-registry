"""Call the WebSub hub to register topics and (re)subscribe the connector callback.

Hub contract (typical): ``hub.mode`` in ``register`` | ``subscribe`` with form body.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..auth.registry import get_auth_strategy
from ..models import ConnectorDefinition

_logger = logging.getLogger(__name__)

_DEFAULT_EVENT_SUFFIXES = (
    "WEBSUB_INDIVIDUAL_CREATED",
    "WEBSUB_INDIVIDUAL_UPDATED",
    "WEBSUB_GROUP_CREATED",
    "WEBSUB_GROUP_UPDATED",
)


def _resolve_topics(cfg: dict[str, Any]) -> list[str]:
    raw = cfg.get("topics")
    if isinstance(raw, list) and raw:
        return [str(t) for t in raw]
    partner = (cfg.get("partner_id") or "").strip()
    if not partner:
        return []
    return [f"{partner}/{suf}" for suf in _DEFAULT_EVENT_SUFFIXES]


def _normalize_hub_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if not u:
        return ""
    if not u.endswith("/hub"):
        if u.endswith("/"):
            u = u + "hub"
        else:
            u = u + "/hub"
    return u


async def sync_subscriptions_with_hub(cd: ConnectorDefinition) -> dict[str, Any]:
    """Register (best-effort) and subscribe every resolved topic at ``hub_url``.

    Uses ``auth_type`` / ``auth_secret_json`` for Bearer token and
    ``webhook_secret`` as ``hub.secret`` for subscribe.
    """
    if cd.transport_type != "websub":
        raise ValueError("Only transport_type=websub supports hub subscription sync")

    cfg = cd.get_source_config()
    hub_url = _normalize_hub_url(cfg.get("hub_url", ""))
    callback = (cfg.get("callback_url") or "").strip()
    topics = _resolve_topics(cfg)

    if not hub_url:
        raise ValueError("source_config_json.hub_url is required")
    if not callback:
        raise ValueError("source_config_json.callback_url is required")
    if not topics:
        raise ValueError(
            "No topics: set source_config_json.topics or source_config_json.partner_id"
        )
    strategy = get_auth_strategy(cd.auth_type)
    auth_ctx = await strategy.get_auth_context(cd)
    headers: dict[str, str] = dict(auth_ctx.headers)

    topic_results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        for topic in topics:
            entry: dict[str, Any] = {"topic": topic}

            try:
                reg = await client.post(
                    hub_url,
                    data={"hub.mode": "register", "hub.topic": topic},
                    headers=headers,
                )
                entry["register_http_status"] = reg.status_code
                entry["register_ok"] = reg.status_code in (200, 201, 204)
                if not entry["register_ok"]:
                    entry["register_body_preview"] = (reg.text or "")[:500]
            except Exception as e:
                entry["register_ok"] = False
                entry["register_error"] = str(e)

            try:
                sub_data: dict[str, str] = {
                    "hub.mode": "subscribe",
                    "hub.topic": topic,
                    "hub.callback": callback,
                }
                if (cd.webhook_secret or "").strip():
                    sub_data["hub.secret"] = cd.webhook_secret
                sub = await client.post(
                    hub_url,
                    data=sub_data,
                    headers=headers,
                )
                entry["subscribe_http_status"] = sub.status_code
                entry["subscribe_ok"] = sub.status_code in (200, 201, 202, 204)
                if not entry["subscribe_ok"]:
                    entry["subscribe_body_preview"] = (sub.text or "")[:500]
            except Exception as e:
                entry["subscribe_ok"] = False
                entry["subscribe_error"] = str(e)

            topic_results.append(entry)
            _logger.info(
                "WebSub sync topic=%s register=%s subscribe=%s",
                topic,
                entry.get("register_http_status"),
                entry.get("subscribe_http_status"),
            )

    all_sub_ok = all(t.get("subscribe_ok") for t in topic_results)
    return {
        "connector_id": cd.connector_id,
        "hub_url": hub_url,
        "callback_url": callback,
        "topics_attempted": topics,
        "all_subscribe_ok": all_sub_ok,
        "results": topic_results,
    }
