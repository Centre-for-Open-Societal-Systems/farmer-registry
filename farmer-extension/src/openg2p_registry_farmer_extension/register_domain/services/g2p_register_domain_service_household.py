import logging

from openg2p_registry_core.services import G2PRegisterDomainService
from sqlalchemy import select

from .domain_validation_utils import as_bool, as_int, validation_error

_logger = logging.getLogger("g2p-register-domain-service")

HOUSEHOLD_REGISTER_ID = "9055ab43-c85d-4833-bd00-ca657bb72644"


class G2PRegisterDomainServiceHousehold(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._normalize_booleans(record)
            self._validate_household_size(record)

    @staticmethod
    def _normalize_booleans(record: dict) -> None:
        # The checkbox widget submits '' rather than null/false when left
        # untouched, which Postgres rejects as an invalid boolean literal.
        for field in ("father_included", "mother_included", "other_land_owner"):
            if not isinstance(record.get(field), bool):
                record[field] = as_bool(record.get(field)) or False

    def _validate_household_size(self, record: dict) -> None:
        size_of_group = as_int(record.get("size_of_group"))
        male = as_int(record.get("number_of_male_members"))
        female = as_int(record.get("number_of_female_members"))
        children = as_int(record.get("number_of_children"))

        for field_name, value in (
            ("size_of_group", size_of_group),
            ("number_of_male_members", male),
            ("number_of_female_members", female),
            ("number_of_children", children),
        ):
            if value is not None and value < 0:
                validation_error(f"{field_name} must not be negative")

        if size_of_group is not None and male is not None and female is not None:
            if size_of_group != male + female:
                validation_error(
                    "size_of_group must equal number_of_male_members + number_of_female_members"
                )

        if size_of_group is not None and children is not None and children > size_of_group:
            validation_error("number_of_children must not exceed size_of_group")

        if as_bool(record.get("father_included")) and male is not None and male < 1:
            validation_error(
                "number_of_male_members must be at least one when father_included is true"
            )
        if as_bool(record.get("mother_included")) and female is not None and female < 1:
            validation_error(
                "number_of_female_members must be at least one when mother_included is true"
            )

    async def post_ingest(self, register_id, register_row, session):
        """Finish head synchronization when a new Household follows its Farmer intake row."""
        if register_id != HOUSEHOLD_REGISTER_ID:
            return

        from ..models import G2PRegisterFarmer

        household_head = (
            await session.execute(
                select(G2PRegisterFarmer)
                .where(
                    G2PRegisterFarmer.link_internal_record_id
                    == register_row.internal_record_id,
                    G2PRegisterFarmer.is_household_head.is_(True),
                )
                .order_by(
                    G2PRegisterFarmer.created_at.asc(),
                    G2PRegisterFarmer.internal_record_id.asc(),
                )
            )
        ).scalars().first()
        if household_head:
            register_row.household_head = household_head.record_name

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for household")

        keys = [
            "functional_record_id",
            "record_name",
            "household_head",
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
        _logger.info("Constructing record name for household")

        keys = ["household_head", "functional_record_id"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
