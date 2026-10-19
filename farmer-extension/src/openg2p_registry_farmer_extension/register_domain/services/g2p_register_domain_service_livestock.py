import logging
from decimal import Decimal, InvalidOperation

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import (
    active_records,
    is_blank,
    normalized_text,
    reject_duplicates,
    validation_error,
)
from .validation_rules import is_interactive

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceLivestock(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in active_records(records):
            self._validate_row(record)
        self._validate_no_duplicate_livestock_type(records)

    @staticmethod
    def _validate_row(record: dict) -> None:
        # The section is optional, but a row a staff member adds must identify
        # an animal and its count. Keep incomplete legacy import rows compatible.
        for field, label in (("livestock_type", "Livestock Type"), ("head_count", "Head Count")):
            if is_interactive(record) and is_blank(record.get(field)):
                validation_error(f"{label} is required for every livestock record")
        if not is_blank(record.get("livestock_type")):
            record["livestock_type"] = str(record["livestock_type"]).strip()
        if is_blank(record.get("head_count")):
            if "head_count" in record:
                record["head_count"] = None
            return
        raw = record["head_count"]
        try:
            count = Decimal(str(raw))
        except InvalidOperation:
            validation_error("Head Count must be a nonnegative whole number")
        if (
            isinstance(raw, bool)
            or not count.is_finite()
            or count != count.to_integral_value()
            or not 0 <= count <= 2147483647
        ):
            validation_error("Head Count must be a whole number between 0 and 2147483647")
        record["head_count"] = int(count)

    def _validate_no_duplicate_livestock_type(self, records: list[dict]) -> None:
        reject_duplicates(
            records,
            lambda record: normalized_text(record.get("livestock_type")),
            "The same Livestock Type is listed more than once; each type needs its own row",
        )

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for livestock")

        keys = [
            "livestock_type",
            "breed",
            "head_count",
            "livestock_system",
            "gender",
            "body_condition",
            "production_type",
        ]
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
        _logger.info("Constructing record name for livestock")

        keys = ["livestock_type", "breed"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
