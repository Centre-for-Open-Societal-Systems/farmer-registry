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


def patch(path):
    source = path.read_text()
    if source.count(NEW) == 1:
        return
    if source.count(OLD) != 1:
        raise RuntimeError("Platform ingestion changed; review ODK signature integration")
    result = source.replace(OLD, NEW)
    compile(result, str(path), "exec")
    path.write_text(result)


if __name__ == "__main__":
    spec = importlib.util.find_spec("openg2p_registry_core")
    patch(Path(spec.origin).parent / "services/g2p_ingest_service.py")
