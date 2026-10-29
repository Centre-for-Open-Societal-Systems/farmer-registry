"""Domain service of the FarmerPhone register (models/farmer_phone.py)."""

from openg2p_registry_core.services import G2PRegisterDomainService
from openg2p_registry_farmer_extension.openg2p_farmer.register_domain.services.domain_validation_utils import (
    as_bool,
    is_blank,
    validation_error,
)

from ..derived import normalize_phone
from .derivations import Derivations, refresh_farmer, refresh_farmers_of


def _join(payload: dict, keys) -> str:
    return " ".join(str(payload.get(k)).strip() for k in keys if not is_blank(payload.get(k)))


class FarmerPhoneService(Derivations, G2PRegisterDomainService):
    """A farmer's phone numbers. Kept as the national number plus E.164, one
    number once per farmer, at most one primary; the farmer's phone list
    follows them."""

    async def validate_domain_attributes(self, records: list[dict]):
        await self.derive(records)
        primaries, numbers = 0, set()
        for record in records:
            if is_blank(record.get("phone_number")):
                validation_error("Phone Number: a row has no number. Enter the number, or remove the row")
            if record.get("is_primary"):
                primaries += 1
            if record["phone_number"] in numbers:
                validation_error("Phone Number: the same number is listed twice. Keep one row for it and remove the other")
            numbers.add(record["phone_number"])
        if primaries > 1:
            validation_error("Primary: more than one number is marked primary. Tick Primary for one number only")

    async def derive(self, records: list[dict]) -> None:
        for record in records:
            if "is_primary" in record:
                record["is_primary"] = bool(as_bool(record.get("is_primary")))
            if is_blank(record.get("phone_number")):
                continue
            if is_blank(record.get("country_code")):
                record["country_code"] = "ET"
            national, e164 = normalize_phone(record["phone_number"], record["country_code"])
            if national is None:
                validation_error(f"Phone Number: {record['phone_number']} is not a phone number. Enter it as 0912345678 or +251912345678")
            record["phone_number"], record["phone_e164"] = national, e164

    async def pre_approve(self, change_request, session):
        await self.derive_payload(change_request, session)

    async def post_approve(self, change_request, session):
        await refresh_farmers_of(change_request, session)

    async def post_ingest(self, register_id, register_row, session):
        national, e164 = normalize_phone(register_row.phone_number, register_row.country_code)
        if national:
            register_row.phone_number, register_row.phone_e164 = national, e164
        await refresh_farmer(session, register_row.link_internal_record_id)

    def construct_search_text(self, payload: dict, extra: list[str] | None = None) -> str:
        return " ".join([*(extra or []), _join(payload, ("phone_type", "phone_number", "phone_e164"))]).strip()

    def construct_record_name(self, payload: dict, extra: list[str] | None = None) -> str:
        return " ".join([*(extra or []), _join(payload, ("phone_type", "phone_number"))]).strip() or "Phone"
