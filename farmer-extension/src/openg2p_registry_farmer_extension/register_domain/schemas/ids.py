from typing import Optional
from sqlalchemy import Date, String, select

from openg2p_registry_core.schemas import (
    G2PRegisterBaseSchema, G2PPersonSchema, G2PGeoSchema,
    G2PRegisterHistorySchema, G2PPersonHistorySchema, G2PGeoHistorySchema,
    G2PIntakeFormSchemaBase
)
from ..models.enums import (
    DisabilityTypeEnum,
    DisabilitySeverityEnum,
    EducationalLevelEnum,
    SourceOfIncomeEnum,
)

class G2PSchemaIds:
    
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    expiry_date: Optional[Date] = None
    status: Optional[str] = None
    description: Optional[str] = None

class G2PRegisterSchemaIds(G2PRegisterBaseSchema, G2PPersonSchema, G2PGeoSchema, G2PSchemaIds):
    """
    Schema for Farmer register.
    Inherits fields from G2PRegisterBaseSchema, G2PPersonSchema, and G2PGeoSchema.
    Attributes inherited from G2PSchemaFarmer are specific to the Farmer domain.
    """


class G2PRegisterHistorySchemaIds(G2PRegisterHistorySchema, G2PPersonHistorySchema, G2PGeoHistorySchema):
    """
    Schema for Farmer history.
    Inherits fields from G2PRegisterHistorySchema, G2PPersonHistorySchema, and G2PGeoHistorySchema.
    Attributes specific to the Farmer domain are not included in the history schema as they are not expected to change over time.
    """

class G2PIntakeFormSchemaIds(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PPersonSchema, G2PGeoSchema, G2PSchemaIds):
    """
    Schema for Farmer intake form.
    Inherits fields from G2PRegisterBaseSchema, G2PPersonSchema, and G2PGeoSchema.
    Attributes inherited from G2PSchemaFarmer are specific to the Farmer domain and are included in the intake form schema for data collection.
    """
