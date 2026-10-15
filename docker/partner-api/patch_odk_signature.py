"""Bind verification to the pinned platform's resolved partner/signature path."""
import importlib.util
from pathlib import Path

OLD = "        return incoming_partner, signature, signature_payload, incoming_model_key_path\n"
NEW = '''        if data_model_id == "FARMER_ODK_MODEL":
            from openg2p_registry_farmer_extension.odk_signature import verify_odk_signature
            from ..helpers.partner_management import get_partner_mgmt_settings
            await verify_odk_signature(
                incoming_partner.partner_id, signature, signature_payload, ingest_data,
                get_partner_mgmt_settings().partner_mgmt_api_url,
            )
        return incoming_partner, signature, signature_payload, incoming_model_key_path
'''
DEDUPE_OLD = "            correlation_id = uuid.uuid4().hex\n"
DEDUPE_NEW = '''            if data_model.data_model_id == "FARMER_ODK_MODEL":
                if not isinstance(message_id, str) or not message_id:
                    raise ValueError("Farmer ODK message ID is required")
                # Serialize retries for this partner/source event within the
                # same transaction as the intake write; no schema migration.
                await session.execute(select(func.pg_advisory_xact_lock(
                    func.hashtext("farmer-odk:" + incoming_partner.partner_id),
                    func.hashtext(message_id),
                )))
                existing = (await session.execute(select(IncomingRawData).where(
                    IncomingRawData.partner_id == incoming_partner.partner_id,
                    IncomingRawData.data_model_id == data_model.data_model_id,
                    IncomingRawData.ingest_message_id == message_id,
                ).order_by(IncomingRawData.receipt_date_time).limit(1))).scalar_one_or_none()
                if existing is not None:
                    stored = await session.get(IncomingRawDataPayload, existing.ingest_id)
                    if stored.raw_data_json.get("body", {}).get("message") != ingest_data.get("body", {}).get("message"):
                        raise ValueError("Farmer ODK source event was reused with different data")
                    response_store_id = None
                    if data_model.response_template_document_id:
                        from .g2p_template_service import G2PTemplateService
                        response_store_id = await G2PTemplateService.get_component().resolve_template_store_id(
                            session, data_model.response_template_document_id)
                    return existing.ingest_correlation_id, response_store_id
            correlation_id = uuid.uuid4().hex
'''


def patch(path):
    source = path.read_text()
    if source.count(NEW) == 1:
        if source.count(DEDUPE_NEW) == 1:
            return
        if source.count(DEDUPE_OLD) != 1:
            raise RuntimeError("Platform ingestion dedupe changed; review integration")
        result = source.replace(DEDUPE_OLD, DEDUPE_NEW)
        compile(result, str(path), "exec")
        path.write_text(result)
        return
    if source.count(OLD) != 1:
        raise RuntimeError("Platform ingestion changed; review ODK signature integration")
    result = source.replace(OLD, NEW)
    if DEDUPE_OLD in result:
        result = result.replace(DEDUPE_OLD, DEDUPE_NEW)
    compile(result, str(path), "exec")
    path.write_text(result)


if __name__ == "__main__":
    spec = importlib.util.find_spec("openg2p_registry_core")
    patch(Path(spec.origin).parent / "services/g2p_ingest_service.py")
