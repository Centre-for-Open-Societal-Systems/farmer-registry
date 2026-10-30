"""Derived values on the farmer registers, kept in step on every way in.

validate_domain_attributes changes the records it is given. On the intake form
those are the rows that are saved; a change request validates a copy, so
pre_approve applies the same changes to the stored payload (as the farmer
extension does for disability details). Values that depend on other records
(a farmer's land totals and phones) are refreshed after
approval and after ingestion.

Dates are Gregorian everywhere they are entered; each register lists its dates
that also keep an Ethiopian calendar twin in ethiopic_dates, and the twin is
derived on every way in.
"""

import base64
import hashlib
import io
import json
import logging
import uuid
from collections import OrderedDict

from openg2p_registry_core.models import G2PRegisterChangeRequestPayload
from openg2p_registry_core.models.enum import ChangeActionEnum
from openg2p_registry_farmer_extension.openg2p_farmer.register_domain.services.domain_validation_utils import (
    as_bool,
    is_blank,
    validation_error,
)
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from ..derived import (
    ethiopic_of,
    email_of,
    ethiopic_twin,
    farmer_search_text,
    geo_names,
    hectares,
    land_rollup,
    local_name_problems,
    normalize_phone,
    sync_email,
)
from ..name_rules import NAME_LABELS, name_problems

_logger = logging.getLogger("oan-derivations")


def _json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


async def _payload_records(change_request, session):
    payload = await session.get(G2PRegisterChangeRequestPayload, change_request.change_request_id)
    if not payload or not payload.change_payload:
        return None, []
    skip = {ChangeActionEnum.DELETE.value, ChangeActionEnum.NO_CHANGE.value}
    return payload, [r for r in payload.change_payload if r.get("edit_action") not in skip]


async def farmers_of(change_request, session) -> set[str]:
    """The farmers a change request touches: the record itself, for a farmer
    section, or the rows' parent, for a table section such as lands."""
    payload = await session.get(G2PRegisterChangeRequestPayload, change_request.change_request_id)
    ids = {change_request.internal_record_id}
    ids.update(r.get("link_internal_record_id") for r in (payload.change_payload or []) if payload)
    return {i for i in ids if i}


async def refresh_farmers_of(change_request, session) -> None:
    for farmer_id in await farmers_of(change_request, session):
        await refresh_farmer(session, farmer_id)


class Derivations:
    """The Ethiopian calendar twins of a register's dates; the end of every
    register's derivation chain."""

    # (Gregorian date field, Ethiopian calendar twin field)
    ethiopic_dates: tuple[tuple[str, str], ...] = ()

    async def derive(self, records: list[dict]) -> None:
        for record in records:
            for gc_field, ec_field in self.ethiopic_dates:
                ethiopic_twin(record, gc_field, ec_field)

    async def post_ingest(self, register_id, register_row, session):
        await super().post_ingest(register_id, register_row, session)
        for gc_field, ec_field in self.ethiopic_dates:
            setattr(register_row, ec_field, ethiopic_of(getattr(register_row, gc_field)))

    async def derive_payload(self, change_request, session) -> None:
        payload, records = await _payload_records(change_request, session)
        if records:
            await self.derive(records)
            flag_modified(payload, "change_payload")


# --- Farmer -----------------------------------------------------------------


def _farmer_record(record: dict) -> None:
    if "geo_code_hierarchy_json" in record:
        record.update(geo_names(_json(record.get("geo_code_hierarchy_json"))))
    if "is_household_head" in record:
        record["is_household_head"] = as_bool(record.get("is_household_head"))
    if problems := name_problems(record) + local_name_problems(record) + sync_email(record):
        validation_error("; ".join(problems))


async def refresh_farmer(session, farmer_id: str | None) -> None:
    """Land totals and phone list of one farmer, from its own approved rows.

    The household head is the household's attribute and changes only through a
    change request on the household (household_intake.py), never from here."""
    from ..models import (
        G2PRegisterFarmer,
        G2PRegisterFarmerPhone,
        G2PRegisterLand,
    )

    farmer = await session.get(G2PRegisterFarmer, farmer_id) if farmer_id else None
    if farmer is None:
        return

    lands = (await session.execute(
        select(G2PRegisterLand.land_ownership_type, G2PRegisterLand.land_size, G2PRegisterLand.unit).where(
            G2PRegisterLand.link_internal_record_id == farmer_id, G2PRegisterLand.record_status == "ACTIVE")
    )).all()
    for field, value in land_rollup((kind, hectares(size, unit)) for kind, size, unit in lands).items():
        setattr(farmer, field, value)

    # The phone rows are the source; the farmer's phone_numbers list (used by
    # search and deduplication) follows them. A farmer without phone rows, such
    # as one that came with a phone list from a partner, keeps the list.
    phones = (await session.execute(
        select(G2PRegisterFarmerPhone).where(
            G2PRegisterFarmerPhone.link_internal_record_id == farmer_id,
            G2PRegisterFarmerPhone.record_status == "ACTIVE",
        ).order_by(G2PRegisterFarmerPhone.is_primary.desc().nulls_last(), G2PRegisterFarmerPhone.created_at)
    )).scalars().all()
    if phones:
        farmer.phone_numbers = [
            {"type": str(p.phone_type or "other").lower(), "number": p.phone_e164 or p.phone_number,
             "is_primary": index == 0}
            for index, p in enumerate(phones)
        ]
        farmer.has_personal_phone = True


async def _phones_from_list(farmer, session) -> None:
    """Phone rows for an ingested farmer that brought only a phone list."""
    from ..models import G2PRegisterFarmerPhone

    entries = _json(farmer.phone_numbers) or []
    if not entries or not isinstance(entries, list):
        return
    existing = (await session.execute(
        select(G2PRegisterFarmerPhone.internal_record_id).where(
            G2PRegisterFarmerPhone.link_internal_record_id == farmer.internal_record_id).limit(1)
    )).first()
    if existing:
        return
    for index, entry in enumerate(e for e in entries if isinstance(e, dict)):
        national, e164 = normalize_phone(entry.get("number"), farmer.country_code)
        if not national:
            continue
        session.add(G2PRegisterFarmerPhone(
            internal_record_id=str(uuid.uuid4()),
            link_internal_record_id=farmer.internal_record_id,
            phone_type="PRIMARY" if entry.get("is_primary") or index == 0 else "SECONDARY",
            phone_number=national, phone_e164=e164, country_code=farmer.country_code or "ET",
            is_primary=bool(entry.get("is_primary")) or index == 0,
            record_status="ACTIVE", created_by=farmer.created_by, created_at=farmer.created_at,
            last_approved_by=farmer.last_approved_by, last_approved_at=farmer.last_approved_at,
        ))
    await session.flush()


async def check_household_heads(change_request, session) -> None:
    """A farmer change request that makes the farmer a household's head is
    approved only once that household names the farmer as its head."""
    from ..models import G2PRegisterFarmer
    from .household_intake import farmer_name, registered_household_head_problems

    _, records = await _payload_records(change_request, session)
    problems = []
    for record in records:
        if not as_bool(record.get("is_household_head")):
            continue
        farmer_id = record.get("internal_record_id") or change_request.internal_record_id
        stored = await session.get(G2PRegisterFarmer, farmer_id) if farmer_id else None
        merged = {**(stored.to_dict() if stored is not None else {}), **record, "internal_record_id": farmer_id}
        problems += await registered_household_head_problems(
            session, merged, merged.get("link_internal_record_id"), farmer_name(merged))
    if problems:
        validation_error("; ".join(problems))


class FarmerDerivations(Derivations):
    ethiopic_dates = (("birth_date", "birth_date_ec"),)

    def construct_search_text(self, payload: dict, extra: list[str] | None = None) -> str:
        return farmer_search_text(payload, extra)

    async def derive(self, records: list[dict]) -> None:
        for record in records:
            _farmer_record(record)
        await super().derive(records)

    async def pre_approve(self, change_request, session):
        await self.derive_payload(change_request, session)
        await check_household_heads(change_request, session)
        await super().pre_approve(change_request, session)

    async def post_approve(self, change_request, session):
        await super().post_approve(change_request, session)
        await refresh_farmers_of(change_request, session)

    async def post_ingest(self, register_id, register_row, session):
        await super().post_ingest(register_id, register_row, session)
        row = register_row
        for field, value in geo_names(_json(row.geo_code_hierarchy_json)).items():
            setattr(row, field, value)
        # The enumerator is whoever submitted the form, on the day it was begun,
        # unless the source (ODK, a partner) said who it was.
        if is_blank(row.enumerator_name):
            row.enumerator_name = row.created_by
        if row.data_collection_date is None and row.created_at is not None:
            row.data_collection_date = row.created_at.date()
        if is_blank(row.email):
            row.email = email_of(row.emails)
        await _phones_from_list(row, session)
        await refresh_farmer(session, row.internal_record_id)


# --- Land ---------------------------------------------------------------------

# Uploaded certificates by content hash: a change request is validated before
# it is approved, and both steps must store one document, not two.
_uploaded: "OrderedDict[str, str]" = OrderedDict()
_UPLOADED_MAX = 256


def _is_embedded_file(value) -> bool:
    value = _json(value) if isinstance(value, str) and value.startswith("{") else value
    return isinstance(value, dict) and value.get("__type") == "File"


def _store_document(value, created_by) -> str:
    """Store a file the table's file column embedded in the row; its document id.

    The section file uploader covers a section's own file widgets, not files in
    table cells, so the land certificate arrives inline (base64) and is stored
    here the way core stores uploads.
    """
    from openg2p_registry_core.config import Settings
    from openg2p_registry_core.helpers.document import get_document_handler
    from openg2p_registry_core.helpers.file_validation import validate_file_bytes
    from openg2p_registry_core.helpers.file_validation_profiles import (
        get_upload_validation_profile,
    )
    from openg2p_registry_core.models.enum import DocumentBucket

    value = _json(value)
    try:
        content = base64.b64decode(value.get("data") or "", validate=True)
    except ValueError:
        validation_error("Land Certificate: the file could not be read. Attach the file again, or choose another copy")
    digest = hashlib.sha256(content).hexdigest()
    if digest in _uploaded:
        _uploaded.move_to_end(digest)
        return _uploaded[digest]
    filename = value.get("name") or "certificate"
    content_type = value.get("type") or "application/octet-stream"
    profile = get_upload_validation_profile(DocumentBucket.DOCUMENTS, Settings.get_config(strict=False))
    if profile is not None:
        content_type = validate_file_bytes(content, profile, filename=filename).mime_type
    store_id = get_document_handler().upload(
        data=io.BytesIO(content), length=len(content), bucket=DocumentBucket.DOCUMENTS, content_type=content_type)
    document_id = str(uuid.uuid4())
    _pending_documents.append({"document_id": document_id, "document_store_id": store_id,
                               "source_filename": filename, "created_by": str(created_by or "system")})
    _uploaded[digest] = document_id
    while len(_uploaded) > _UPLOADED_MAX:
        _uploaded.popitem(last=False)
    return document_id


_pending_documents: list[dict] = []


async def _save_pending_documents() -> None:
    """Record stored certificates in the document table, in their own session."""
    if not _pending_documents:
        return
    from openg2p_fastapi_common.context import dbengine
    from openg2p_registry_core.models import G2PRegistryDocument
    from openg2p_registry_core.models.enum import DocumentBucket
    from sqlalchemy.ext.asyncio import async_sessionmaker

    rows, _pending_documents[:] = list(_pending_documents), []
    async with async_sessionmaker(dbengine.get(), expire_on_commit=False)() as session:
        for row in rows:
            session.add(G2PRegistryDocument(bucket=DocumentBucket.DOCUMENTS, **row))
        await session.commit()


def _land_record(record: dict) -> None:
    if "land_size" in record or "unit" in record:
        record["area_in_hectare"] = hectares(record.get("land_size"), record.get("unit"))
    if "certificate_storage_id" in record:
        if _is_embedded_file(record["certificate_storage_id"]):
            record["certificate_storage_id"] = _store_document(record["certificate_storage_id"], record.get("created_by"))
        record["certificate_provided"] = not is_blank(record.get("certificate_storage_id"))


class LandDerivations(Derivations):
    async def derive(self, records: list[dict]) -> None:
        for record in records:
            _land_record(record)
        await _save_pending_documents()
        await super().derive(records)

    async def pre_approve(self, change_request, session):
        await self.derive_payload(change_request, session)
        await super().pre_approve(change_request, session)

    async def post_approve(self, change_request, session):
        await super().post_approve(change_request, session)
        await refresh_farmers_of(change_request, session)

    async def post_ingest(self, register_id, register_row, session):
        await super().post_ingest(register_id, register_row, session)
        register_row.area_in_hectare = hectares(register_row.land_size, register_row.unit)
        register_row.certificate_provided = not is_blank(register_row.certificate_storage_id)
        await refresh_farmer(session, register_row.link_internal_record_id)


# --- Crop, livestock, household -------------------------------------------------


class _DatesOnly(Derivations):
    async def pre_approve(self, change_request, session):
        await self.derive_payload(change_request, session)
        await super().pre_approve(change_request, session)


class CropDerivations(_DatesOnly):
    ethiopic_dates = (("planted_date", "planted_date_ec"),)


class LivestockDerivations(_DatesOnly):
    ethiopic_dates = (("collected_date", "collected_date_ec"),)


class HouseholdMemberDerivations(_DatesOnly):
    ethiopic_dates = (("birth_date", "birth_date_ec"),)

    async def derive(self, records: list[dict]) -> None:
        members = {f: NAME_LABELS[f] for f in ("first_name", "middle_name", "last_name")}
        for record in records:
            if problems := name_problems(record, members):
                validation_error("; ".join(problems))
        await super().derive(records)


def _household_record(record: dict) -> None:
    # An untouched yes/no select submits ''; that is "not answered", not "no".
    for field in ("father_included", "mother_included"):
        if field in record:
            record[field] = as_bool(record.get(field))


class HouseholdDerivations(Derivations):
    async def derive(self, records: list[dict]) -> None:
        for record in records:
            _household_record(record)
        await super().derive(records)

    async def pre_approve(self, change_request, session):
        await self.derive_payload(change_request, session)
        await super().pre_approve(change_request, session)


# register mnemonic -> derivations of the farmer extension's service
DERIVATIONS = {
    "Farmer": FarmerDerivations,
    "Land": LandDerivations,
    "Crop": CropDerivations,
    "Livestock": LivestockDerivations,
    "Household": HouseholdDerivations,
    "HouseholdMember": HouseholdMemberDerivations,
}
