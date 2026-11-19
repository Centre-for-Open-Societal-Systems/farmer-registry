"""Read the published message out of a WebSub hub delivery, before the connector's data_path.

The hub delivers the publisher's message as a JSON string in ``hub.content``, which JMESPath cannot parse. A WebSub
connector whose source config sets ``websub_content_envelope: true`` gets that string parsed first; every other
connector keeps upstream's behaviour. Ported from docker/registry-connector's openg2p_registry_connector_extension,
with its test cases (test/runtime/test_connector_media.py).
"""
import json
from typing import Any

from openg2p_connector_service.services.ingestion_service import IngestionService

_MARK = "_oan_websub_content"


def unwrap(raw_data: dict[str, Any]) -> dict[str, Any]:
    content = raw_data.get("hub.content")
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, dict):
        raise ValueError("WebSub content must be a JSON object")
    return content


def install():
    original = IngestionService._extract_envelope
    if getattr(original, _MARK, False):
        return

    def _extract_envelope(self, connector, raw_data):
        if connector.transport_type == "websub" and connector.get_source_config().get("websub_content_envelope"):
            raw_data = unwrap(raw_data)
        return original(self, connector, raw_data)

    setattr(_extract_envelope, _MARK, True)
    IngestionService._extract_envelope = _extract_envelope
