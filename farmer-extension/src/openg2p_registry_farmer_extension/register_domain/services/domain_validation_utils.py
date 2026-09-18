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

from .ethiopian_calendar import (
    ethiopic_to_gregorian,
    format_ethiopic,
    gregorian_to_ethiopic_string,
    parse_ethiopic,
)


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


# Coordinates. The platform stores latitude/longitude as VARCHAR (G2PGeo), but
# the number widget submits a float, and asyncpg refuses to bind a float to a
# VARCHAR parameter ("expected str, got float"). Every intake save of a
# section carrying coordinates then failed with SYS-ERR-001 UNEXPECTED_ERROR
# and no hint of why. Canonicalise here, on every path.
COORDINATE_BOUNDS = {
    "latitude": (-90.0, 90.0),
    "longitude": (-180.0, 180.0),
}
COORDINATE_LABELS = {"latitude": "Latitude", "longitude": "Longitude", "altitude": "Altitude"}


def _format_coordinate(value: float) -> str:
    # 7 decimals is ~1 cm, and what the form's number widget shows; trim the
    # trailing zeros so 9.03 is stored as "9.03", not "9.0300000".
    text = f"{value:.7f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def normalize_coordinates(record: dict) -> None:
    """Coerce latitude/longitude/altitude to the string form the columns hold.

    Only keys the caller sent are touched (an absent key is a partial update).
    Blank clears the value; anything non-numeric or out of range is rejected
    with a message that names the field in the form's own words.
    """
    for field in ("latitude", "longitude", "altitude"):
        if field not in record:
            continue
        raw = record.get(field)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            record[field] = None
            continue
        label = COORDINATE_LABELS[field]
        value = as_float(raw)
        if value is None:
            validation_error(f"{label} must be a number in decimal degrees, e.g. 9.0300")
        bounds = COORDINATE_BOUNDS.get(field)
        if bounds and not bounds[0] <= value <= bounds[1]:
            validation_error(f"{label} must be between {bounds[0]:g} and {bounds[1]:g}")
        record[field] = _format_coordinate(value)


def sync_ethiopic_date_pair(record: dict, gc_field: str, ec_field: str, label: str) -> None:
    """Keep a Gregorian date column and its Ethiopic twin in step.

    Runs in the domain services rather than in the date widget so every entry
    path gets it -- web intake, bulk ingestion, the partner API and file import
    all land in validate_domain_attributes, and only the first of those has a
    UI. Whichever side the enumerator filled derives the other. If both arrive,
    they must agree: silently rewriting one of two explicitly entered values
    would hide a data-entry error rather than surface it.

    Only touches the pair when the caller submitted at least one of them, so a
    partial update of some other field never has a date derived onto it.
    """
    has_gc = gc_field in record
    has_ec = ec_field in record
    if not has_gc and not has_ec:
        return

    gregorian = parse_date(record.get(gc_field))
    raw_ec = record.get(ec_field)
    ethiopic = parse_ethiopic(raw_ec)

    if raw_ec not in (None, "") and ethiopic is None:
        validation_error(f"{label} (EC) must be an Ethiopian date written as YYYY-MM-DD, e.g. 2015-01-05")

    if ethiopic is not None:
        try:
            converted = ethiopic_to_gregorian(*ethiopic)
        except ValueError:
            validation_error(
                f"{label} (EC) {format_ethiopic(*ethiopic)} is not a real Ethiopian date "
                "(months 1-12 have 30 days, Pagumen has 5 or 6)"
            )
        if gregorian is None:
            record[gc_field] = converted
        elif converted != gregorian:
            validation_error(
                f"{label} (EC) does not match {label} (GC): "
                f"{format_ethiopic(*ethiopic)} EC is {converted.isoformat()} GC, "
                f"not {gregorian.isoformat()}"
            )
        # Normalize to the padded string form even when it round-trips, so a
        # legacy date value or an unpadded entry is rewritten on save.
        record[ec_field] = format_ethiopic(*ethiopic)
    elif gregorian is not None:
        record[ec_field] = gregorian_to_ethiopic_string(gregorian)
    else:
        # Both blank: store NULL, not '' (a String column happily keeps '').
        for field in (gc_field, ec_field):
            if field in record:
                record[field] = None
