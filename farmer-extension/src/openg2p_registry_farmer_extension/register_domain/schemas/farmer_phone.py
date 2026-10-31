
from openg2p_registry_core.schemas import (
    G2PIntakeFormSchemaBase,
    G2PRegisterBaseSchema,
    G2PRegisterHistorySchema,
)


class G2PSchemaFarmerPhone:
    phone_type: str | None = None
    phone_number: str | None = None
    country_code: str | None = None
    is_primary: bool | None = None
    phone_e164: str | None = None


class G2PRegisterSchemaFarmerPhone(G2PRegisterBaseSchema, G2PSchemaFarmerPhone):
    """A farmer's phone number."""


class G2PRegisterHistorySchemaFarmerPhone(G2PRegisterHistorySchema):
    """History of a farmer's phone number."""


class G2PIntakeFormSchemaFarmerPhone(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaFarmerPhone):
    """A farmer's phone number on the intake form."""
