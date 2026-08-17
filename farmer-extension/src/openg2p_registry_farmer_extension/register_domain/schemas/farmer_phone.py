from typing import Optional

from openg2p_registry_core.schemas import (
    G2PIntakeFormSchemaBase,
    G2PRegisterBaseSchema,
    G2PRegisterHistorySchema,
)

from ..models.enums import PhoneTypeEnum


class G2PSchemaFarmerPhone:
    phone_type: PhoneTypeEnum
    phone_number: str
    is_primary: Optional[bool] = False
    country_code: Optional[str] = None


class G2PRegisterSchemaFarmerPhone(G2PRegisterBaseSchema, G2PSchemaFarmerPhone):
    pass


class G2PRegisterHistorySchemaFarmerPhone(
    G2PRegisterHistorySchema, G2PSchemaFarmerPhone
):
    pass


class G2PIntakeFormSchemaFarmerPhone(
    G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaFarmerPhone
):
    pass
