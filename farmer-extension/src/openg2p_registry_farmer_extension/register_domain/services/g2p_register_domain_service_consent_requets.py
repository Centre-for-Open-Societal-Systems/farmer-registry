import logging

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import parse_date, validation_error

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceConsentRequests(G2PRegisterDomainService):

    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._validate_valid_dates(record)

    def _validate_valid_dates(self, record: dict) -> None:
        valid_from = parse_date(record.get("valid_from"))
        valid_until = parse_date(record.get("valid_until"))

        if (
            valid_from is not None
            and valid_until is not None
            and valid_until < valid_from
        ):
            validation_error(
                "valid_until must not be earlier than valid_from"
            )

    def construct_search_text(
        self, payload: dict, extra: list[str] = None
    ) -> str:
        _logger.info("Constructing search text for consent requests")

        keys = [
            "consent_creation_request",
            "partner",
            "consent_type",
            "status",
            "valid_from",
            "valid_until",
            "created_at",
        ]

        search_text = []

        if extra:
            search_text.extend(
                str(value).strip()
                for value in extra
                if str(value).strip()
            )

        search_text.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(search_text).strip()

    def construct_record_name(
        self, payload: dict, extra: list[str] = None
    ) -> str:
        _logger.info("Constructing record name for consent requests")

        keys = [
            "consent_creation_request",
            "partner",
        ]

        record_name = []

        if extra:
            record_name.extend(
                str(item).strip()
                for item in extra
                if str(item).strip()
            )

        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()