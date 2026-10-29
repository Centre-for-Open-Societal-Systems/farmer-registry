import logging
from datetime import date

from openg2p_registry_core.models import G2PRegisterChangeRequest
from openg2p_registry_core.models.enum import ChangeActionEnum
from openg2p_registry_core.services import G2PRegisterDomainService
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified


from .domain_validation_utils import as_bool, as_int, fallback_record_name, parse_date, validate_enum_values, validation_error
from .utils.household_roster import (
    CHANGED_PERSON_KIND_FARMER,
    calculate_age,
    recompute_household_for_ingested_row,
    recompute_households_for_change_request,
)

_logger = logging.getLogger("g2p-register-domain-service")



def _enum_fields() -> dict:
    # Imported lazily: ..models imports these services at module level, so a
    # top-level import here would be circular whenever services load first.
    from ..models.enums import DisabilitySeverityEnum, DisabilityTypeEnum, EducationalLevelEnum, SourceOfIncomeEnum

    return {"disability_type": DisabilityTypeEnum, "disability_severity": DisabilitySeverityEnum, "source_of_income": SourceOfIncomeEnum, "education_level": EducationalLevelEnum}


class G2PRegisterDomainServiceFarmer(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            # Drop details before the enum check so a hidden type/severity is
            # removed rather than rejected when the person is not disabled.
            self._clear_disability_details_when_not_disabled(record)
            validate_enum_values(record, _enum_fields())
            self._validate_birth_date(record)
            self._validate_estimated_age(record)

    @staticmethod
    def _clear_disability_details_when_not_disabled(record: dict) -> bool:
        if "disabled" not in record:
            return False
        if as_bool(record.get("disabled")) is True:
            return False
        record["disability_type"] = None
        record["disability_severity"] = None
        return True

    def _validate_birth_date(self, record: dict) -> None:
        birth_date = parse_date(record.get("birth_date"))
        if birth_date is not None and birth_date > date.today():
            validation_error("birth_date must not be in the future")

    def _validate_estimated_age(self, record: dict) -> None:
        birth_date = parse_date(record.get("birth_date"))
        estimated_age = as_int(record.get("estimated_age"))
        if birth_date is None or estimated_age is None:
            return
        computed_age = calculate_age(birth_date)
        if computed_age is not None and abs(estimated_age - computed_age) > 1:
            validation_error(
                "estimated_age must be consistent with birth_date within one year"
            )

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for farmer")

        keys = [
            "functional_record_id",
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
            "language_spoken",
            "source_of_income",
            "national_id_masked",
            "disability_type",
            "latitude",
            "longitude",
            "altitude",
            "plus_code",
            "address_line_1",
            "address_line_2",
            "postal_code",
            "country_code",
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
        _logger.info("Constructing record name for farmer")

        keys = ["first_name", "last_name"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip() or fallback_record_name(payload, "Farmer")

    async def pre_approve(self, change_request: G2PRegisterChangeRequest, session: AsyncSession):
        from openg2p_registry_core.models import G2PRegisterChangeRequestPayload

        from ..models.farmer import G2PRegisterFarmer

        payload_obj = await session.get(
            G2PRegisterChangeRequestPayload, change_request.change_request_id
        )
        if payload_obj and payload_obj.change_payload:
            cleared = False
            for record in payload_obj.change_payload:
                if record.get("edit_action") in {
                    ChangeActionEnum.DELETE.value,
                    ChangeActionEnum.NO_CHANGE.value,
                }:
                    continue
                if self._clear_disability_details_when_not_disabled(record):
                    cleared = True
            if cleared:
                flag_modified(payload_obj, "change_payload")

        await recompute_households_for_change_request(
            session,
            change_request,
            model=G2PRegisterFarmer,
            changed_person_kind=CHANGED_PERSON_KIND_FARMER,
        )

    async def post_ingest(self, register_id: str, register_row, session: AsyncSession):
        await recompute_household_for_ingested_row(session, register_row)
