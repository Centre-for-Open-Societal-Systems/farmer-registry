from typing import Optional
from sqlalchemy import Date, String, select

from openg2p_registry_core.schemas import (
    G2PRegisterBaseSchema,
    G2PPersonSchema,
    G2PGeoSchema,
    G2PRegisterHistorySchema,
    G2PPersonHistorySchema,
    G2PGeoHistorySchema,
    G2PIntakeFormSchemaBase
)
from ..models.enums import (
    DisabilityTypeEnum,
    DisabilitySeverityEnum,
    EducationalLevelEnum,
    SourceOfIncomeEnum,
)


class G2PSchemaConsentReceipts:
    id: Optional[int] = None
    consent_request: Optional[str] = None
    consent_partner: Optional[str] = None
    status: Optional[str] = None
    signature_algorithm: Optional[str] = None
    signed_at: Optional[Date] = None
    actions: Optional[str] = None


class G2PRegisterSchemaConsentReceipts(
    G2PRegisterBaseSchema,
    G2PPersonSchema,
    G2PGeoSchema,
    G2PSchemaConsentReceipts
):
    """
    Schema for Consent Receipts register.
    Inherits fields from G2PRegisterBaseSchema, G2PPersonSchema,
    G2PGeoSchema, and G2PSchemaConsentReceipts.
    """


class G2PRegisterHistorySchemaConsentReceipts(
    G2PRegisterHistorySchema,
    G2PPersonHistorySchema,
    G2PGeoHistorySchema
):
    """
    Schema for Consent Receipts history.
    Inherits fields from G2PRegisterHistorySchema,
    G2PPersonHistorySchema, and G2PGeoHistorySchema.
    """


class G2PIntakeFormSchemaConsentReceipts(
    G2PIntakeFormSchemaBase,
    G2PRegisterBaseSchema,
    G2PPersonSchema,
    G2PGeoSchema,
    G2PSchemaConsentReceipts
):
    """
    Schema for Consent Receipts intake form.
    Inherits fields from G2PRegisterBaseSchema, G2PPersonSchema,
    G2PGeoSchema, and G2PSchemaConsentReceipts.
    """