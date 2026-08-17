import base64
import io
import uuid
from datetime import date, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker

from openg2p_fastapi_common.context import dbengine
from openg2p_registry_core.config import Settings
from openg2p_registry_core.errors import G2PRegistryErrorCodes, G2PRegistryException
from openg2p_registry_core.helpers.document import get_document_handler
from openg2p_registry_core.helpers.file_validation import validate_file_bytes
from openg2p_registry_core.helpers.file_validation_profiles import get_upload_validation_profile
from openg2p_registry_core.models import G2PRegistryDocument
from openg2p_registry_core.models.enum import DocumentBucket


def validation_error(message: str) -> None:
    raise G2PRegistryException(
        code=G2PRegistryErrorCodes.REQUEST_VALIDATION_ERROR.value[1],
        message=message,
    )


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_bool(value) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return bool(value)


def is_embedded_file(value) -> bool:
    """True for the {"__type": "File", "data": "<base64>", ...} shape the
    'file' widget embeds directly in its value on pick, rather than uploading
    it separately through /documents/upload_documents."""
    return isinstance(value, dict) and value.get("__type") == "File"


async def upload_embedded_file(value: dict, created_by) -> str:
    """Upload an embedded-file value's bytes through the same path
    G2PDocumentService.upload_documents uses, and return the resulting
    document_id. Raises via validation_error() on undecodable content."""
    try:
        content = base64.b64decode(value.get("data") or "", validate=True)
    except Exception:
        validation_error("uploaded file could not be decoded")
        return ""

    filename = value.get("name") or "upload"
    content_type = value.get("type") or "application/octet-stream"

    config = Settings.get_config(strict=False)
    profile = get_upload_validation_profile(DocumentBucket.DOCUMENTS, config)
    if profile is not None:
        validation = validate_file_bytes(content, profile, filename=filename)
        content_type = validation.mime_type

    handler = get_document_handler()
    document_store_id = handler.upload(
        data=io.BytesIO(content),
        length=len(content),
        bucket=DocumentBucket.DOCUMENTS,
        content_type=content_type,
    )

    session_maker = async_sessionmaker(dbengine.get(), expire_on_commit=False)
    async with session_maker() as session:
        document_row = G2PRegistryDocument(
            document_id=str(uuid.uuid4()),
            document_store_id=document_store_id,
            bucket=DocumentBucket.DOCUMENTS,
            source_filename=filename,
            created_by=str(created_by or "system"),
        )
        session.add(document_row)
        await session.commit()
        return document_row.document_id


def is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False
