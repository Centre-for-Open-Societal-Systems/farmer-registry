import logging
from datetime import date

from sqlalchemy import select, update

from openg2p_registry_core.models import G2PRegisterChangeRequest
from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import (
    as_float,
    as_int,
    is_embedded_file,
    upload_embedded_file,
    validation_error,
)

_logger = logging.getLogger("g2p-register-domain-service")

LAND_REGISTER_ID = "493153d5-07ef-4743-8efd-07f4099772b9"

# Farmer-level rollups sum land_size across mixed units, so every row is
# normalized to hectares first (matching the fixed-hectare unit the rollup
# implicitly assumed before LandSizeUnitEnum existed).
UNIT_TO_HECTARES = {
    "HECTARE": 1.0,
    "ACRE": 0.404686,
    "SQUARE_METER": 0.0001,
    "SQUARE_KM": 100.0,
    "SQUARE_FOOT": 0.0000092903,
    "SQUARE_YARD": 0.0000836127,
}


class G2PRegisterDomainServiceLand(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            await self._persist_embedded_certificate(record)
            self._synchronize_area_in_hectare(record)
            self._synchronize_certificate_flag(record)
            self._validate_land_size(record)
            self._validate_year_of_acquisition(record)
            self._normalize_numeric_fields(record)

    @staticmethod
    def _normalize_numeric_fields(record: dict) -> None:
        # Number widgets submit '' rather than null when left blank, which
        # Postgres rejects as an invalid integer/numeric literal.
        for field in ("area_in_hectare", "land_size"):
            record[field] = as_float(record.get(field))
        record["year_of_acquisition"] = as_int(record.get("year_of_acquisition"))

    @staticmethod
    async def _persist_embedded_certificate(record: dict) -> None:
        """The 'file' widget embeds a freshly-picked file as a base64 blob
        directly in its value rather than uploading it separately, so left
        as-is that blob would land straight in the certificate_storage_id
        text column instead of a real document reference. Swap it for a
        document_id before the record is persisted. A plain string (an
        existing document_id, or None) passes through unchanged."""
        value = record.get("certificate_storage_id")
        if not is_embedded_file(value):
            return
        record["certificate_storage_id"] = await upload_embedded_file(
            value, record.get("created_by")
        )

    def _synchronize_area_in_hectare(self, record: dict) -> None:
        """Keep the requested hectare UI field and legacy size/unit aligned."""
        area = as_float(record.get("area_in_hectare"))
        size = as_float(record.get("land_size"))
        unit = str(record.get("unit") or "HECTARE")
        if area is None and size is not None:
            area = size * UNIT_TO_HECTARES.get(unit, 1.0)
            record["area_in_hectare"] = round(area, 6)
        elif area is not None:
            record["land_size"] = round(area, 6)
            record["unit"] = "HECTARE"

    @staticmethod
    def _synchronize_certificate_flag(record: dict) -> None:
        # certificate_provided is derived, not user-entered: it always
        # reflects whether a certificate document is actually on file, so the
        # UI shows it read-only rather than letting it drift out of sync with
        # an upload.
        record["certificate_provided"] = bool(
            str(record.get("certificate_storage_id") or "").strip()
        )

    def _validate_land_size(self, record: dict) -> None:
        land_size = as_float(record.get("land_size"))
        if land_size is not None and land_size <= 0:
            validation_error("land_size must be greater than zero when provided")

    def _validate_year_of_acquisition(self, record: dict) -> None:
        year = as_int(record.get("year_of_acquisition"))
        if year is not None and year > date.today().year:
            validation_error("year_of_acquisition must not be in the future")

    async def post_approve(self, change_request: G2PRegisterChangeRequest, session):
        """Recompute the parent farmer's land rollups after any land CR is approved."""
        if change_request.section_register_id != LAND_REGISTER_ID:
            return
        await self._recompute_farmer_land_rollups(change_request.internal_record_id, session)

    async def _recompute_farmer_land_rollups(self, land_internal_record_id: str, session) -> None:
        from ..models import G2PRegisterLand, G2PRegisterFarmer

        land_row = (
            await session.execute(
                select(G2PRegisterLand).where(
                    G2PRegisterLand.internal_record_id == land_internal_record_id
                )
            )
        ).scalar()
        farmer_id = land_row.link_internal_record_id if land_row else None
        if not farmer_id:
            return

        all_lands = (
            await session.execute(
                select(G2PRegisterLand).where(
                    G2PRegisterLand.link_internal_record_id == farmer_id,
                    G2PRegisterLand.record_status == "ACTIVE",
                )
            )
        ).scalars().all()

        by_ownership = {"OWNER": 0.0, "TENANT": 0.0, "OTHER": 0.0}
        ownership_types_present = set()
        for land in all_lands:
            size = as_float(land.land_size)
            if size is None:
                continue
            hectares = size * UNIT_TO_HECTARES.get(land.unit, 1.0)
            bucket = land.land_ownership_type if land.land_ownership_type in ("OWNER", "TENANT") else "OTHER"
            by_ownership[bucket] += hectares
            if land.land_ownership_type:
                ownership_types_present.add(land.land_ownership_type)

        total_owned = by_ownership["OWNER"]
        total_rented = by_ownership["TENANT"]
        # CROP_SHARE and FAMILY_GIFT land is neither owned nor rented outright;
        # it still counts toward total area under "crop sharing".
        total_crop_share = by_ownership["OTHER"]
        total_area = total_owned + total_rented + total_crop_share

        if not ownership_types_present:
            land_ownership = None
        elif ownership_types_present == {"OWNER"}:
            land_ownership = "OWNER"
        elif ownership_types_present == {"TENANT"}:
            land_ownership = "TENANT"
        else:
            land_ownership = "HYBRID"

        await session.execute(
            update(G2PRegisterFarmer)
            .where(G2PRegisterFarmer.internal_record_id == farmer_id)
            .values(
                total_land_area=round(total_area, 6),
                total_land_owned_area=round(total_owned, 6),
                total_land_rent_area=round(total_rented, 6),
                total_land_crop_sharing_area=round(total_crop_share, 6),
                land_ownership=land_ownership,
            )
        )

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for land")

        keys = [
            "land_ownership_type",
            "land_size",
            "area_in_hectare",
            "land_kebele",
            "certificate_provided",
            "certificate_storage_id",
            "unit",
            "current_land_use",
            "farming_type",
            "means_of_acquisition",
            "land_id",
            "latitude",
            "longitude",
            "altitude",
            "plus_code",
            "address_line_1",
            "address_line_2",
            "postal_code",
            "country_code",
            "shape_type",
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
        _logger.info("Constructing record name for land")

        keys = ["land_size", "unit", "current_land_use"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
