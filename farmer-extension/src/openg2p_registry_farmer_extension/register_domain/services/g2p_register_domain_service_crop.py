import logging
from datetime import date

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import (
    active_records,
    is_blank,
    normalized_text,
    parse_date,
    reject_duplicates,
    sync_ethiopic_date_pair,
    validation_error,
)
from .validation_rules import is_interactive

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceCrop(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            sync_ethiopic_date_pair(record, "planted_date", "planted_date_ec", "Planted Date")
            self._validate_planted_date(record)
        for record in active_records(records):
            self._validate_required(record)
        self._validate_no_duplicate_commodity(records)

    def _validate_planted_date(self, record: dict) -> None:
        planted_date = parse_date(record.get("planted_date"))
        if planted_date is not None and planted_date > date.today():
            validation_error("Planted Date cannot be in the future")

    @staticmethod
    def _validate_required(record: dict) -> None:
        """A crop row needs at least what it is and when it is grown
        -- a row of blanks or spaces is not a crop. Bulk import and
        the partner API carry whatever the legacy record held, so -- as for
        the farmer's names -- the check is for form paths only."""
        if not is_interactive(record):
            return
        for field, label in (("commodity", "Commodity"), ("season", "Season")):
            if is_blank(record.get(field)):
                validation_error(f"{label} is required for every crop")
            record[field] = str(record[field]).strip()

    def _validate_no_duplicate_commodity(self, records: list[dict]) -> None:
        # Ethiopia double-crops: the same commodity grown in Meher and again
        # in Belg is two legitimate rows. What is a duplicate is the same
        # commodity twice in one season.
        def key(record: dict):
            commodity = normalized_text(record.get("commodity"))
            if commodity is None:
                return None
            return commodity, normalized_text(record.get("season"))

        reject_duplicates(
            records,
            key,
            "The same Commodity is listed more than once for the same Season; "
            "a crop grown in two seasons needs one row per season",
        )

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for crop")

        keys = [
            "commodity",
            "season",
            "end_use",
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
        _logger.info("Constructing record name for crop")

        keys = ["commodity", "season"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
