import logging

from openg2p_registry_core.models import (
    G2PRegisterChangeRequest,
    G2PRegisterChangeRequestPayload,
)
from openg2p_registry_core.services import G2PRegisterDomainService
from sqlalchemy import select, update

from .domain_validation_utils import is_blank, validation_error
from .validation_rules import PHONE_COUNTRY_CODE, normalize_phone, phone_e164

_logger = logging.getLogger("g2p-register-domain-service")

FARMER_PHONE_REGISTER_ID = "c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f"


class G2PRegisterDomainServiceFarmerPhone(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        # The checkbox widget submits '' rather than null/false when left
        # untouched, which Postgres rejects as an invalid boolean literal.
        for record in records:
            if not isinstance(record.get("is_primary"), bool):
                record["is_primary"] = False

        active_records = [
            record
            for record in records
            if str(record.get("edit_action") or "").upper() != "DELETE"
        ]
        for record in active_records:
            if is_blank(record.get("phone_type")):
                validation_error("Phone Type is required for every phone number")
            if is_blank(record.get("phone_number")):
                validation_error("Phone Number is required")
            # phone_number holds the national significant number only and the
            # country lives in country_code (the Gen2 storage model). Gen1's E.164 values
            # and the trunk-0 local form are both accepted and reduced to the
            # 9 digits, so one number is stored one way whichever form it
            # arrived in -- the batch dedup groups on it.
            national = normalize_phone(record["phone_number"])
            if national is None:
                validation_error(
                    "Phone Number must be an Ethiopian number, e.g. 0912345678 "
                    "or +251912345678"
                )
            record["phone_number"] = national
            record["phone_e164"] = phone_e164(national)
            if is_blank(record.get("country_code")):
                record["country_code"] = PHONE_COUNTRY_CODE

        if sum(bool(record.get("is_primary")) for record in active_records) > 1:
            validation_error("Only one phone number can be the primary phone")

    async def post_approve(self, change_request: G2PRegisterChangeRequest, session):
        if change_request.section_register_id != FARMER_PHONE_REGISTER_ID:
            return
        payload = (
            await session.execute(
                select(G2PRegisterChangeRequestPayload).where(
                    G2PRegisterChangeRequestPayload.change_request_id
                    == change_request.change_request_id
                )
            )
        ).scalar_one_or_none()
        preferred_primary_id = next(
            (
                record.get("internal_record_id")
                for record in ((payload.change_payload or []) if payload else [])
                if str(record.get("edit_action") or "").upper() != "DELETE"
                and bool(record.get("is_primary"))
            ),
            None,
        )
        await self._sync_parent_phone_projection(
            change_request.internal_record_id,
            session,
            preferred_primary_id=preferred_primary_id,
        )

    async def post_ingest(self, register_id, register_row, session):
        """Apply the same projection after an approved intake is ingested."""
        if register_id != FARMER_PHONE_REGISTER_ID:
            return
        # Ingest does not always pass through validate_domain_attributes
        # (partner and ODK payloads), so normalise the row that landed. A
        # value that is not a recognisable Ethiopian number is left as sent
        # rather than failing an approved intake; the boot migration logs it.
        national = normalize_phone(register_row.phone_number)
        if national:
            register_row.phone_number = national
            register_row.phone_e164 = phone_e164(national)
            if is_blank(register_row.country_code):
                register_row.country_code = PHONE_COUNTRY_CODE
        farmer_internal_record_id = register_row.link_internal_record_id
        if not farmer_internal_record_id:
            return
        await self._sync_parent_phone_projection(
            farmer_internal_record_id,
            session,
            preferred_primary_id=(
                register_row.internal_record_id if register_row.is_primary else None
            ),
        )

    async def _sync_parent_phone_projection(
        self,
        farmer_internal_record_id,
        session,
        preferred_primary_id=None,
    ):
        from ..models import G2PRegisterFarmer, G2PRegisterFarmerPhone

        if preferred_primary_id:
            await session.execute(
                update(G2PRegisterFarmerPhone)
                .where(
                    G2PRegisterFarmerPhone.link_internal_record_id
                    == farmer_internal_record_id,
                    G2PRegisterFarmerPhone.internal_record_id
                    != preferred_primary_id,
                    G2PRegisterFarmerPhone.record_status == "ACTIVE",
                )
                .values(is_primary=False)
            )

        phones = (
            await session.execute(
                select(G2PRegisterFarmerPhone)
                .where(
                    G2PRegisterFarmerPhone.link_internal_record_id
                    == farmer_internal_record_id,
                    G2PRegisterFarmerPhone.record_status == "ACTIVE",
                )
                .order_by(
                    G2PRegisterFarmerPhone.is_primary.desc(),
                    G2PRegisterFarmerPhone.created_at.asc(),
                )
            )
        ).scalars().all()
        if phones and not any(item.is_primary for item in phones):
            phones[0].is_primary = True

        projection = [
            {
                "type": str(item.phone_type).lower(),
                "number": item.phone_number,
                "e164": item.phone_e164 or phone_e164(normalize_phone(item.phone_number)),
                "is_primary": bool(item.is_primary),
            }
            for item in phones
        ]
        await session.execute(
            update(G2PRegisterFarmer)
            .where(
                G2PRegisterFarmer.internal_record_id == farmer_internal_record_id
            )
            .values(
                phone_numbers=projection or None,
                has_personal_phone=bool(projection),
            )
        )

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        values = list(extra or [])
        values.extend(
            payload.get(key) for key in ("phone_type", "phone_number")
        )
        return " ".join(str(value).strip() for value in values if value).strip()

    def construct_record_name(self, payload: dict, extra: list[str] = None) -> str:
        values = list(extra or [])
        values.extend(
            payload.get(key) for key in ("phone_type", "phone_number")
        )
        return " ".join(str(value).strip() for value in values if value).strip()
