import logging
from datetime import date

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import (
    active_records,
    is_blank,
    parse_date,
    reject_duplicates,
    sync_ethiopic_date_pair,
    validation_error,
)
from .validation_rules import ID_TYPE_MESSAGES, ID_TYPE_PATTERNS, matches

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceRegId(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._validate_value_required(record)
            self._validate_value_format(record)
            sync_ethiopic_date_pair(record, "expiry_date", "expiry_date_ec", "Expiry Date")
        for record in active_records(records):
            self._validate_not_expired_when_valid(record)
        reject_duplicates(
            records,
            self._id_key,
            "The same ID is listed more than once; each ID Type and Value can be "
            "recorded only once, with a single Status",
        )

    @staticmethod
    def _id_key(record: dict):
        """(type, value) with the value written the way it is compared: a FAN
        is the same number with or without its FAN- prefix."""
        if is_blank(record.get("id_type")) or is_blank(record.get("value")):
            return None
        id_type = str(record["id_type"]).strip().upper()
        value = str(record["value"]).strip().upper()
        if value.startswith("FAN-"):
            value = value[4:]
        return id_type, value

    @staticmethod
    def _validate_not_expired_when_valid(record: dict) -> None:
        # An expired document cannot be a valid ID. The enumerator
        # either records it as Invalid or corrects the date.
        if str(record.get("status") or "").strip().upper() != "VALID":
            return
        expiry = parse_date(record.get("expiry_date"))
        if expiry is not None and expiry < date.today():
            validation_error(
                f"This ID expired on {expiry.isoformat()}, so its Status cannot be "
                "Valid; set Status to Invalid or correct the Expiry Date"
            )

    def _validate_value_required(self, record: dict) -> None:
        if not is_blank(record.get("id_type")) and is_blank(record.get("value")):
            validation_error("ID Value is required when an ID Type is selected")

    def _validate_value_format(self, record: dict) -> None:
        """Check the ID value against the rule for its own type.

        The form cannot do this: widget-data-validation puts a single pattern on
        the whole value column, and validation.ts implements neither `custom`
        nor `zodSchema`, so per-type rules exist server-side only.

        A type with no rule registered is accepted rather than rejected --
        the ODK ACK types are not described yet, and guessing their format
        would lock staff out of recording them entirely.
        """
        id_type = str(record.get("id_type") or "").strip().upper()
        pattern = ID_TYPE_PATTERNS.get(id_type)
        if pattern is None:
            return
        value = record.get("value")
        if is_blank(value):
            return
        record["value"] = str(value).strip()
        if not matches(pattern, record["value"]):
            validation_error(
                f"ID Value is not a valid {id_type}: {ID_TYPE_MESSAGES[id_type]}"
            )

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for registrant id")

        keys = ["id_type", "value", "status"]
        search_text = []
        if extra:
            search_text.extend(
                str(value).strip() for value in extra if str(value).strip()
            )
        search_text.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(search_text).strip()

    def construct_record_name(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing record name for registrant id")

        keys = ["id_type", "value"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
