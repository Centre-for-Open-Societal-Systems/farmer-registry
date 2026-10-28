"""Supported synchronous ODK enricher: documents, stable land links and household lookup."""
import base64
import io
from copy import deepcopy
from uuid import uuid4

from openg2p_registry_core.interfaces import G2PPayloadEnricherInterface
from sqlalchemy import select

from .transform import intake_sections


def store_file(value, session, created_by):
    from openg2p_registry_core.config import Settings
    from openg2p_registry_core.helpers.document import get_document_handler
    from openg2p_registry_core.helpers.file_validation import validate_file_bytes
    from openg2p_registry_core.helpers.file_validation_profiles import (
        get_upload_validation_profile,
    )
    from openg2p_registry_core.models import G2PRegistryDocument
    from openg2p_registry_core.models.enum import DocumentBucket

    try:
        content = base64.b64decode(value.get("data") or "", validate=True)
    except (ValueError, TypeError):
        raise ValueError("ODK attachment: unreadable file; resend the submission with its attachment") from None
    if not content:
        raise ValueError("ODK attachment: empty file; resend the submission with its attachment")
    filename = value.get("name") or "attachment"
    content_type = value.get("type") or "application/octet-stream"
    profile = get_upload_validation_profile(DocumentBucket.DOCUMENTS, Settings.get_config(strict=False))
    if profile is not None:
        content_type = validate_file_bytes(content, profile, filename=filename).mime_type
    store_id = get_document_handler().upload(data=io.BytesIO(content), length=len(content),
        bucket=DocumentBucket.DOCUMENTS, content_type=content_type)
    document_id = str(uuid4())
    session.add(G2PRegistryDocument(document_id=document_id, document_store_id=store_id,
        bucket=DocumentBucket.DOCUMENTS, source_filename=filename, created_by=created_by))
    # The native enrichment transaction owns commit/rollback; no global cache,
    # independent DB transaction or reference to another ingest's documents.
    return document_id


def replace_files(value, session, actor):
    if isinstance(value, dict):
        if value.get("__type") == "File":
            return store_file(value, session, actor)
        return {key: replace_files(item, session, actor) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_files(item, session, actor) for item in value]
    return value


class OdkToFarmerIntakeEnricher(G2PPayloadEnricherInterface):
    def enrich(self, data, session):
        from ..register_domain.models import G2PRegisterFarmer

        raw = deepcopy(data.get("payload", data))
        raw.pop("oan_household_id", None)
        raw.pop("oan_intake_sections", None)
        actor = (raw.get("survey_metadata") or {}).get("enumerator_name") or \
            (raw.get("__system") or {}).get("submitterName") or "system"
        raw = replace_files(raw, session, str(actor))
        lands = (raw.get("land_info") or {}).get("land_info_repeat") or raw.get("land_info_repeat") or []
        for land in lands:
            land["oan_land_id"] = str(uuid4())
        questions = raw.get("household_questions") or {}
        if str(questions.get("household_head", "")).lower() in ("no", "false", "0") and \
                str(questions.get("head_registered", "")).lower() in ("yes", "true", "1"):
            reference = questions.get("member_reference_id") or raw.get("member_reference_id")
            matches = session.execute(select(G2PRegisterFarmer).where(
                G2PRegisterFarmer.odk_farmer_id == str(reference or ""),
                G2PRegisterFarmer.record_status == "ACTIVE",
                G2PRegisterFarmer.is_household_head.is_(True))).scalars().all()
            if len(matches) != 1 or not matches[0].link_internal_record_id:
                raise ValueError("Household head: enter the ODK Farmer ID of one approved registered head with a household")
            raw["oan_household_id"] = matches[0].link_internal_record_id
        raw["oan_intake_sections"] = intake_sections(raw)
        return raw
