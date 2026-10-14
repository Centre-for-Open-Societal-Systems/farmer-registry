import logging

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import is_blank, validation_error

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceConsentReceipt(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._validate_signature_present(record)

    def _validate_signature_present(self, record: dict) -> None:
        if not is_blank(record.get("signed_at")) and is_blank(record.get("signature")):
            validation_error("signature is required when signed_at is set")

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for consent receipt")

        keys = ["related_consent_request_id", "status"]
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
        _logger.info("Constructing record name for consent receipt")

        keys = ["related_consent_request_id", "status"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
