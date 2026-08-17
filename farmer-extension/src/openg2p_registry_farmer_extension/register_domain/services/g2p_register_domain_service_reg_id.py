import logging

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import is_blank, validation_error

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceRegId(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._validate_value_required(record)

    def _validate_value_required(self, record: dict) -> None:
        if not is_blank(record.get("id_type")) and is_blank(record.get("value")):
            validation_error("value is required when id_type is set")

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
