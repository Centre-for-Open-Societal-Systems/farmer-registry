from datetime import date
from typing import Optional

from openg2p_registry_core.schemas import (
    G2PRegisterBaseSchema, G2PPersonSchema, G2PGeoSchema,
    G2PRegisterHistorySchema, G2PPersonHistorySchema, G2PGeoHistorySchema,
    G2PIntakeFormSchemaBase
)
from ..models.enums import (
    DisabilityTypeEnum,
    DisabilitySeverityEnum,
    EducationalLevelEnum,
    FarmerImportSourceEnum,
    SourceOfIncomeEnum,
    FarmerLandOwnershipEnum,
    FarmerStateEnum,
)

class G2PSchemaFarmer:

    state: Optional[FarmerStateEnum] = None
    import_source: Optional[FarmerImportSourceEnum] = None
    birth_date_ec: Optional[date] = None
    estimated_age: Optional[int] = None
    has_personal_phone: Optional[bool] = None
    disabled: Optional[bool] = None
    disability_type: Optional[DisabilityTypeEnum] = None
    disability_severity: Optional[DisabilitySeverityEnum] = None
    source_of_income: Optional[SourceOfIncomeEnum] = None
    source_of_income_other: Optional[str] = None
    language_spoken: Optional[str] = None
    local_language: Optional[str] = None
    education_level: Optional[EducationalLevelEnum] = None
    national_id_masked: Optional[str] = None
    is_psnp_user: Optional[bool] = None
    is_household_head: Optional[bool] = None

    first_name_amh: Optional[str] = None
    middle_name_amh: Optional[str] = None
    last_name_amh: Optional[str] = None
    first_name_om: Optional[str] = None
    middle_name_om: Optional[str] = None
    last_name_om: Optional[str] = None

    enumerator_name: Optional[str] = None
    enumerator_user_id: Optional[str] = None
    data_collection_date: Optional[date] = None
    enumerator_latitude: Optional[float] = None
    enumerator_longitude: Optional[float] = None
    enumerator_altitude: Optional[float] = None
    enumerator_accuracy: Optional[float] = None

    total_land_area: Optional[float] = None
    total_land_owned_area: Optional[float] = None
    total_land_rent_area: Optional[float] = None
    total_land_crop_sharing_area: Optional[float] = None
    land_ownership: Optional[FarmerLandOwnershipEnum] = None

    region_name: Optional[str] = None
    zone_name: Optional[str] = None
    woreda_name: Optional[str] = None
    kebele_name: Optional[str] = None

class G2PRegisterSchemaFarmer(G2PRegisterBaseSchema, G2PPersonSchema, G2PGeoSchema, G2PSchemaFarmer):
    """
    Schema for Farmer register.
    Inherits fields from G2PRegisterBaseSchema, G2PPersonSchema, and G2PGeoSchema.
    Attributes inherited from G2PSchemaFarmer are specific to the Farmer domain.
    """


class G2PRegisterHistorySchemaFarmer(
    G2PRegisterHistorySchema,
    G2PPersonHistorySchema,
    G2PGeoHistorySchema,
    G2PSchemaFarmer,
):
    """
    Schema for Farmer history.
    Inherits fields from G2PRegisterHistorySchema, G2PPersonHistorySchema, and G2PGeoHistorySchema.
    Includes Farmer domain fields so approved changes remain visible in history.
    """

class G2PIntakeFormSchemaFarmer(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PPersonSchema, G2PGeoSchema, G2PSchemaFarmer):
    """
    Schema for Farmer intake form.
    Inherits fields from G2PRegisterBaseSchema, G2PPersonSchema, and G2PGeoSchema.
    Attributes inherited from G2PSchemaFarmer are specific to the Farmer domain and are included in the intake form schema for data collection.
    """
