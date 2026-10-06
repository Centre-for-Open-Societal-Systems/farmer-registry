"""Webhook transport — records arrive via HTTP POST; no polling needed."""

from typing import AsyncIterator

from ..models import ConnectorDefinition
from .base import BaseTransport, SourceRecord
from .checkpoints import CheckpointMode, TransportCapability
from .registry import register_transport


@register_transport("webhook")
class WebhookTransport(BaseTransport):
    # Webhooks are push, not poll. They bypass poll_state_json entirely;
    # the controller writes one IngestionRun per request and idempotency
    # on source_event_id is the only "checkpoint" that matters.
    capability = TransportCapability(
        modes=(),
        default_mode=CheckpointMode.FULL_SCAN,
        supports_strict_incremental=True,
        notes="Push-based; no polling checkpoint applies.",
    )

    async def fetch(
        self, connector: ConnectorDefinition
    ) -> AsyncIterator[SourceRecord]:
        raise NotImplementedError(
            "WebhookTransport does not poll; records are pushed via the webhook controller."
        )
