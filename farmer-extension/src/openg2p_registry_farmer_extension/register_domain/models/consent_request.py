from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from .enums import ConsentTypeEnum, ConsentOriginEnum, ConsentStatusEnum
from ..services import G2PRegisterDomainServiceConsentRequest

class G2PConsentRequest:

    consent_type: Mapped[ConsentTypeEnum] = mapped_column(String, nullable=True)      # ConsentTypeEnum
    consent_partner_name: Mapped[str] = mapped_column(String, nullable=True)          # requesting partner/institution, free text
    purpose: Mapped[str] = mapped_column(Text, nullable=True)
    allowed_data_fields: Mapped[str] = mapped_column(Text, nullable=True)             # free-text list of requested data points
    validity_from: Mapped[str] = mapped_column(DateTime, nullable=True)
    validity_to: Mapped[str] = mapped_column(DateTime, nullable=True)
    originated_from: Mapped[ConsentOriginEnum] = mapped_column(String, nullable=True)     # ConsentOriginEnum
    status: Mapped[ConsentStatusEnum] = mapped_column(String, nullable=True)      # ConsentStatusEnum
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=True)

# All Register classes should have the prefix G2PRegister
class G2PRegisterConsentRequest(G2PRegister, G2PConsentRequest):
    __tablename__ = "g2p_register_consent_requests"

    def get_search_text_fields(self) -> str:
        """Return consent-request fields used to build search_text."""
        return G2PRegisterDomainServiceConsentRequest().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return consent-request record_name from domain service implementation."""
        return G2PRegisterDomainServiceConsentRequest().construct_record_name(self.to_dict())

# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryConsentRequest(G2PRegisterHistory, G2PConsentRequest):
    __tablename__ = "g2p_register_history_consent_requests"

# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormConsentRequest(G2PIntakeForm, G2PRegister, G2PConsentRequest):
    __tablename__ = "g2p_intake_form_consent_requests"

    def get_search_text_fields(self) -> str:
        """Return consent-request fields used to build search_text."""
        return G2PRegisterDomainServiceConsentRequest().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return consent-request record_name from domain service implementation."""
        return G2PRegisterDomainServiceConsentRequest().construct_record_name(self.to_dict())
