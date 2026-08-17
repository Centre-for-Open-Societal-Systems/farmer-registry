import logging

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import as_bool, as_float, validation_error

_logger = logging.getLogger("g2p-register-domain-service")

_AMOUNT_FIELDS = (
    "amount_fertilizer_utilized",
    "amount_pesticide_utilized",
    "amount_insecticide_utilized",
    "amount_improved_seed_utilized",
)

_BOOLEAN_FIELDS = (
    "fertilizer_use",
    "pesticide_use",
    "insecticide_use",
    "improved_seed_use",
    "access_to_machinery",
    "access_to_finance",
)


class G2PRegisterDomainServiceFarmInputs(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._normalize_booleans(record)
            self._validate_amounts(record)

    @staticmethod
    def _normalize_booleans(record: dict) -> None:
        # Select/checkbox widgets submit 'true'/'false' strings or '' for an
        # untouched checkbox, both of which asyncpg rejects for a Boolean
        # column outright.
        for field in _BOOLEAN_FIELDS:
            if not isinstance(record.get(field), bool):
                record[field] = as_bool(record.get(field)) or False

    def _validate_amounts(self, record: dict) -> None:
        # Number widgets submit '' rather than null when left blank, which
        # Postgres rejects as an invalid numeric literal — normalize as part
        # of validating, same as the boolean fields above.
        for field in _AMOUNT_FIELDS:
            amount = as_float(record.get(field))
            record[field] = amount
            if amount is not None and amount < 0:
                validation_error(f"{field} must not be negative")

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for farm inputs")

        keys = [
            "water_source",
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
        _logger.info("Constructing record name for farm inputs")

        keys = ["water_source"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
