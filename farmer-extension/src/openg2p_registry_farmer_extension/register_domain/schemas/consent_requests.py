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


class G2PSchemaConsentRequests:
    consent_creation_request: Optional[str] = None
    partner: Optional[str] = None
    consent_type: Optional[str] = None
    status: Optional[str] = None
    valid_from: Optional[Date] = None
    valid_until: Optional[Date] = None
    created_at: Optional[Date] = None


class G2PRegisterSchemaConsentRequests(
    G2PRegisterBaseSchema,
    G2PPersonSchema,
    G2PGeoSchema,
    G2PSchemaConsentRequests
):
    """
    Schema for Consent Requests register.
    Inherits fields from G2PRegisterBaseSchema, G2PPersonSchema,
    G2PGeoSchema, and G2PSchemaConsentRequests.
    """


class G2PRegisterHistorySchemaConsentRequests(
    G2PRegisterHistorySchema,
    G2PPersonHistorySchema,
    G2PGeoHistorySchema
):
    """
    Schema for Consent Requests history.
    Inherits fields from G2PRegisterHistorySchema,
    G2PPersonHistorySchema, and G2PGeoHistorySchema.
    """


class G2PIntakeFormSchemaConsentRequests(
    G2PIntakeFormSchemaBase,
    G2PRegisterBaseSchema,
    G2PPersonSchema,
    G2PGeoSchema,
    G2PSchemaConsentRequests
):
    """
    Schema for Consent Requests intake form.
    Inherits fields from G2PRegisterBaseSchema, G2PPersonSchema,
    G2PGeoSchema, and G2PSchemaConsentRequests.
    """