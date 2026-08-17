from datetime import datetime
from typing import Optional

from openg2p_registry_core.schemas import G2PRegisterBaseSchema, G2PRegisterHistorySchema, G2PIntakeFormSchemaBase
from ..models.enums import ConsentTypeEnum, ConsentOriginEnum, ConsentStatusEnum


class G2PSchemaConsentRequest:

    consent_type: Optional[ConsentTypeEnum] = None
    consent_partner_name: Optional[str] = None
    purpose: Optional[str] = None
    allowed_data_fields: Optional[str] = None
    validity_from: Optional[datetime] = None
    validity_to: Optional[datetime] = None
    originated_from: Optional[ConsentOriginEnum] = None
    status: Optional[ConsentStatusEnum] = None
    rejection_reason: Optional[str] = None


class G2PRegisterSchemaConsentRequest(G2PRegisterBaseSchema, G2PSchemaConsentRequest):
    """
    Schema for Consent Request register.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaConsentRequest are specific to the Consent Request domain.
    """


class G2PRegisterHistorySchemaConsentRequest(G2PRegisterHistorySchema):
    """
    Schema for Consent Request history.
    Inherits fields from G2PRegisterHistorySchema.
    """


class G2PIntakeFormSchemaConsentRequest(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaConsentRequest):
    """
    Schema for Consent Request intake form.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaConsentRequest are specific to the Consent Request domain and are included in the intake form schema for data collection.
    """
