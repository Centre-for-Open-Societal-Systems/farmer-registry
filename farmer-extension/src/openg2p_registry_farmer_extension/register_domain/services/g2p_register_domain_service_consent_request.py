import logging

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import is_blank, validation_error

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceConsentRequest(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._validate_validity_range(record)

    def _validate_validity_range(self, record: dict) -> None:
        validity_from = record.get("validity_from")
        validity_to = record.get("validity_to")
        if not is_blank(validity_from) and not is_blank(validity_to) and validity_from > validity_to:
            validation_error("validity_from must be earlier than or equal to validity_to")

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for consent request")

        keys = ["consent_type", "consent_partner_name", "status"]
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
        _logger.info("Constructing record name for consent request")

        keys = ["consent_partner_name", "consent_type"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
