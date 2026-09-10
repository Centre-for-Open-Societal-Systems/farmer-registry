from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import Boolean, Date, Integer, Numeric, String, select
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_registry_core.models import (
    G2PRegister, G2PRegisterHistory, G2PGeo, G2PPerson,
    G2PPersonHistory, G2PGeoHistory
)
from ..services import G2PRegisterDomainServiceFarmer
from .enums import (
    DisabilityTypeEnum, DisabilitySeverityEnum, SourceOfIncomeEnum, EducationalLevelEnum,
    FarmerImportSourceEnum, FarmerLandOwnershipEnum, FarmerStateEnum,
)

class G2PFarmer:

    # Workflow/source projections copied from the platform's intake/change
    # request records so they can be displayed and filtered in the Farmer
    # register list without joining workflow tables in the search endpoint.
    state: Mapped[FarmerStateEnum] = mapped_column(String, nullable=True)
    import_source: Mapped[FarmerImportSourceEnum] = mapped_column(String, nullable=True)

    # Ethiopian-calendar date is stored separately from the base G2PPerson
    # Gregorian birth_date so both values can be captured and displayed.
    # Held as a "YYYY-MM-DD" string, not a Date: the Ethiopic year has a 13th
    # month (Pagumen), and both Python's date and Postgres reject month 13
    # outright, so a date column silently cannot represent the ~1.4% of
    # birthdays that fall in it. The string form sorts correctly and
    # round-trips exactly -- see register_domain/services/ethiopian_calendar.py.
    birth_date_ec: Mapped[str] = mapped_column(String, nullable=True)
    estimated_age: Mapped[int] = mapped_column(Integer, nullable=True)
    has_personal_phone: Mapped[bool] = mapped_column(Boolean, nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=True)
    disability_type: Mapped[DisabilityTypeEnum] = mapped_column(String, nullable=True)       # DisabilityTypeEnum
    disability_severity: Mapped[DisabilitySeverityEnum] = mapped_column(String, nullable=True)   # DisabilitySeverityEnum
    source_of_income: Mapped[SourceOfIncomeEnum] = mapped_column(String, nullable=True)      # SourceOfIncomeEnum; use source_of_income_other when OTHERS (Excel)
    source_of_income_other: Mapped[str] = mapped_column(String, nullable=True)
    language_spoken: Mapped[str] = mapped_column(String, nullable=True)       # Attribute lookup; primary language
    local_language: Mapped[str] = mapped_column(String, nullable=True)       # Attribute lookup; local/community language
    education_level: Mapped[EducationalLevelEnum] = mapped_column(String, nullable=True)       # EducationalLevelEnum
    national_id_masked: Mapped[str] = mapped_column(String, nullable=True)
    is_psnp_user: Mapped[bool] = mapped_column(Boolean, nullable=True)  # Productive Safety Net Programme beneficiary
    is_household_head: Mapped[bool] = mapped_column(Boolean, nullable=True)

    # Multi-script name capture, alongside the base G2PPerson English name fields
    first_name_amh: Mapped[str] = mapped_column(String, nullable=True)
    middle_name_amh: Mapped[str] = mapped_column(String, nullable=True)
    last_name_amh: Mapped[str] = mapped_column(String, nullable=True)
    first_name_om: Mapped[str] = mapped_column(String, nullable=True)
    middle_name_om: Mapped[str] = mapped_column(String, nullable=True)
    last_name_om: Mapped[str] = mapped_column(String, nullable=True)

    # Enumerator / data-collection provenance
    enumerator_name: Mapped[str] = mapped_column(String, nullable=True)
    enumerator_user_id: Mapped[str] = mapped_column(String, nullable=True)
    data_collection_date: Mapped[str] = mapped_column(Date, nullable=True)
    enumerator_latitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=True)
    enumerator_longitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=True)
    enumerator_altitude: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
    enumerator_accuracy: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)

    # Land rollups, recomputed from this farmer's Land records whenever a
    # land change request is approved (see G2PRegisterDomainServiceLand.post_approve).
    total_land_area: Mapped[float] = mapped_column(Numeric(16, 6), nullable=True)
    total_land_owned_area: Mapped[float] = mapped_column(Numeric(16, 6), nullable=True)
    total_land_rent_area: Mapped[float] = mapped_column(Numeric(16, 6), nullable=True)
    total_land_crop_sharing_area: Mapped[float] = mapped_column(Numeric(16, 6), nullable=True)
    land_ownership: Mapped[FarmerLandOwnershipEnum] = mapped_column(String, nullable=True)   # FarmerLandOwnershipEnum

    # Flattened out of geo_code_hierarchy_json so the search-result list (which
    # only supports flat getattr(row, field_name) lookups, no JSON paths) can
    # show them as plain columns.
    region_name: Mapped[str] = mapped_column(String, nullable=True)
    zone_name: Mapped[str] = mapped_column(String, nullable=True)
    woreda_name: Mapped[str] = mapped_column(String, nullable=True)
    kebele_name: Mapped[str] = mapped_column(String, nullable=True)

    # Raw geo id (not just the display name) so the Land table's kebele
    # dropdown can filter master-data-api's geo-level-values by this farmer's
    # own woreda via widget dependsOn.
    woreda_level_value_id: Mapped[str] = mapped_column(String, nullable=True)

# All Register classes should have the prefix G2PRegister
class G2PRegisterFarmer(G2PRegister, G2PPerson, G2PGeo, G2PFarmer):
    __tablename__ = "g2p_register_farmers"

    def get_record_name_fields(self) -> str:
        """Return farmer fields used to build record_name."""
        return G2PRegisterDomainServiceFarmer().construct_record_name(self.to_dict())

    def get_search_text_fields(self) -> str:
        """Return farmer fields used to build search_text."""
        return G2PRegisterDomainServiceFarmer().construct_search_text(self.to_dict())

# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryFarmer(G2PRegisterHistory, G2PPersonHistory, G2PGeoHistory, G2PFarmer):
    __tablename__ = "g2p_register_history_farmers"

# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormFarmer(G2PIntakeForm, G2PRegister, G2PPerson, G2PGeo, G2PFarmer):
    __tablename__ = "g2p_intake_form_farmers"

    def get_record_name_fields(self) -> str:
        """Return farmer fields used to build record_name."""
        return G2PRegisterDomainServiceFarmer().construct_record_name(self.to_dict())

    def get_search_text_fields(self) -> str:
        """Return farmer fields used to build search_text."""
        return G2PRegisterDomainServiceFarmer().construct_search_text(self.to_dict())
