"""Wrap the connector's envelope extraction and G2P envelope construction."""

from . import registry_signature, websub_content

_MARK = "_openg2p_registry_connector_extension"


def install(IngestionService=None) -> None:
    if IngestionService is None:
        from openg2p_connector_service.services.ingestion_service import IngestionService

    extract, wrap = IngestionService._extract_envelope, IngestionService._wrap_in_g2p_envelope
    if getattr(extract, _MARK, False):
        return

    def _extract_envelope(self, connector, raw_data):
        cfg = connector.get_source_config()
        if connector.transport_type == "websub" and cfg.get("websub_content_envelope"):
            raw_data = websub_content.unwrap(raw_data)
        return extract(self, connector, raw_data)

    def _wrap_in_g2p_envelope(self, connector, data, *args, **kwargs):
        sign = connector.get_source_config().get("sign_registry_payload")
        if sign and isinstance(data.get("header"), dict) and data["header"].get("sender_id"):
            raise ValueError("Prewrapped payloads are not accepted by a signing connector")
        envelope = wrap(self, connector, data, *args, **kwargs)
        return registry_signature.sign_envelope(connector, envelope) if sign else envelope

    for f in (_extract_envelope, _wrap_in_g2p_envelope):
        setattr(f, _MARK, True)
    IngestionService._extract_envelope = _extract_envelope
    IngestionService._wrap_in_g2p_envelope = _wrap_in_g2p_envelope
