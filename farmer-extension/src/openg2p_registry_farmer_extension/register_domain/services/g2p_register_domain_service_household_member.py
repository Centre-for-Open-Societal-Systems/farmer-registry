import logging
from datetime import date

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import (
    as_bool,
    is_embedded_file,
    parse_date,
    sync_ethiopic_date_pair,
    upload_embedded_file,
    validation_error,
)

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceHouseholdMember(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            # The checkbox widget submits '' rather than null/false when left
            # untouched, which Postgres rejects as an invalid boolean literal.
            if not isinstance(record.get("is_disabled"), bool):
                record["is_disabled"] = as_bool(record.get("is_disabled")) or False
            # Whichever calendar the enumerator used, derive the other before
            # the future-date check so both columns are checked as one date.
            sync_ethiopic_date_pair(record, "birth_date", "birth_date_ec", "Date of birth")
            self._validate_birth_date(record)
            await self._persist_embedded_certificate(record)
            self._synchronize_certificate_flag(record)

    @staticmethod
    async def _persist_embedded_certificate(record: dict) -> None:
        """Same as a land's certificate: the 'file' widget (and the ODK
        connector) embed the picked file as a base64 blob in the value, which
        must become a document_id before it reaches the text column. The
        upload applies the registry's document profile (PDF, JPG, PNG, WebP,
        size cap), so a refused file refuses the save. A plain string (an
        existing document_id, or None) passes through."""
        value = record.get("certificate_storage_id")
        if not is_embedded_file(value):
            return
        record["certificate_storage_id"] = await upload_embedded_file(
            value, record.get("created_by"), purpose="member_certificate"
        )

    @staticmethod
    def _synchronize_certificate_flag(record: dict) -> None:
        # Derived, never typed: it reflects whether a certificate is on file.
        record["certificate_provided"] = bool(
            str(record.get("certificate_storage_id") or "").strip()
        )

    def _validate_birth_date(self, record: dict) -> None:
        birth_date = parse_date(record.get("birth_date"))
        if birth_date is not None and birth_date > date.today():
            validation_error("Date of birth cannot be in the future")

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for household member")

        keys = [
            "first_name",
            "last_name",
            "foundational_id",
            "middle_name",
            "given_name",
            "gender",
            "birth_date",
            "marital_status",
            "occupation",
            "education_level",
            "latitude",
            "longitude",
            "altitude",
            "plus_code",
            "address_line_1",
            "address_line_2",
            "postal_code",
            "country_code",
            "is_disabled",
            "certificate_provided",
        ]
        search_text = []
        if extra:
            search_text.extend(str(item).strip() for item in extra if str(item).strip())
        search_text.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(search_text).strip()

    def construct_record_name(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing record name for household member")

        keys = ["first_name", "last_name"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
