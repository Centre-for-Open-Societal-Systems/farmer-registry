from datetime import datetime
from typing import Optional

from openg2p_registry_core.schemas import G2PRegisterBaseSchema, G2PRegisterHistorySchema, G2PIntakeFormSchemaBase
from ..models.enums import ConsentStatusEnum


class G2PSchemaConsentReceipt:

    related_consent_request_id: Optional[str] = None
    status: Optional[ConsentStatusEnum] = None
    attribute_list: Optional[str] = None
    signature_algorithm: Optional[str] = None
    signature: Optional[str] = None
    signed_at: Optional[datetime] = None


class G2PRegisterSchemaConsentReceipt(G2PRegisterBaseSchema, G2PSchemaConsentReceipt):
    """
    Schema for Consent Receipt register.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaConsentReceipt are specific to the Consent Receipt domain.
    """


class G2PRegisterHistorySchemaConsentReceipt(G2PRegisterHistorySchema):
    """
    Schema for Consent Receipt history.
    Inherits fields from G2PRegisterHistorySchema.
    """


class G2PIntakeFormSchemaConsentReceipt(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaConsentReceipt):
    """
    Schema for Consent Receipt intake form.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaConsentReceipt are specific to the Consent Receipt domain and are included in the intake form schema for data collection.
    """
