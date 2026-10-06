"""WebSub transport.

WebSub is push-based: the hub delivers content to this service's webhook
endpoint, then the normal ingestion pipeline maps and forwards it to the
registry Partner API. The connector stores hub/subscription metadata in
``source_config_json`` for operators, but records are not polled here.
"""

from .checkpoints import CheckpointMode, TransportCapability
from .registry import register_transport
from .webhook import WebhookTransport


@register_transport("websub")
class WebSubTransport(WebhookTransport):
    capability = TransportCapability(
        modes=(),
        default_mode=CheckpointMode.FULL_SCAN,
        supports_strict_incremental=True,
        notes=(
            "Push-based WebSub callback transport; no polling checkpoint applies. "
            "Use /webhook/{connector_id} or /webhook/by-slug/{slug} as the callback URL."
        ),
    )

