from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import Boolean, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Date, String, select
from openg2p_registry_core.models import (
    G2PRegister, G2PRegisterHistory, G2PGeo, G2PPerson,
    G2PPersonHistory, G2PGeoHistory
)
from ..services import G2PRegisterDomainServiceConsentReceipts
from .enums import DisabilityTypeEnum, DisabilitySeverityEnum, SourceOfIncomeEnum, EducationalLevelEnum


class G2PConsentReceipts:

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    consent_receipts: Mapped[str] = mapped_column(String(100), nullable=False)
    consent_partner: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=True)
    signature_algorithm: Mapped[str] = mapped_column(String(100), nullable=True)
    signed_at: Mapped[Date] = mapped_column(Date, nullable=True)

# All Register classes should have the prefix G2PRegister
class G2PRegisterConsentReceipts(
    G2PRegister, G2PPerson, G2PGeo, G2PConsentReceipts
):
    __tablename__ = "g2p_register_consent_receipts"

    def get_record_name_fields(self) -> str:
        """Return farmer fields used to build record_name."""
        return G2PRegisterDomainServiceConsentReceipts().construct_record_name(
            self.to_dict()
        )

    def get_search_text_fields(self) -> str:
        """Return farmer fields used to build search_text."""
        return G2PRegisterDomainServiceConsentReceipts().construct_search_text(
            self.to_dict()
        )


# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryConsentReceipts(
    G2PRegisterHistory,
    G2PPersonHistory,
    G2PGeoHistory,
    G2PConsentReceipts
):
    __tablename__ = "g2p_register_history_consent_receipts"


# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormConsentReceipts(
    G2PIntakeForm,
    G2PRegister,
    G2PPerson,
    G2PGeo,
    G2PConsentReceipts
):
    __tablename__ = "g2p_intake_form_consent_receipts"

    def get_record_name_fields(self) -> str:
        """Return farmer fields used to build record_name."""
        return G2PRegisterDomainServiceConsentReceipts().construct_record_name(
            self.to_dict()
        )

    def get_search_text_fields(self) -> str:
        """Return farmer fields used to build search_text."""
        return G2PRegisterDomainServiceConsentReceipts().construct_search_text(
            self.to_dict()
        )