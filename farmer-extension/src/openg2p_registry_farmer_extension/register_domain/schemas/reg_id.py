from datetime import date
from typing import Optional

from openg2p_registry_core.schemas import G2PRegisterBaseSchema, G2PRegisterHistorySchema, G2PIntakeFormSchemaBase
from ..models.enums import IdTypeEnum, IdStatusEnum


class G2PSchemaRegId:

    id_type: Optional[IdTypeEnum] = None
    value: Optional[str] = None
    expiry_date: Optional[date] = None
    status: Optional[IdStatusEnum] = None
    description: Optional[str] = None


class G2PRegisterSchemaRegId(G2PRegisterBaseSchema, G2PSchemaRegId):
    """
    Schema for Registrant ID register.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaRegId are specific to the Registrant ID domain.
    """


class G2PRegisterHistorySchemaRegId(G2PRegisterHistorySchema):
    """
    Schema for Registrant ID history.
    Inherits fields from G2PRegisterHistorySchema.
    """


class G2PIntakeFormSchemaRegId(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaRegId):
    """
    Schema for Registrant ID intake form.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaRegId are specific to the Registrant ID domain and are included in the intake form schema for data collection.
    """
