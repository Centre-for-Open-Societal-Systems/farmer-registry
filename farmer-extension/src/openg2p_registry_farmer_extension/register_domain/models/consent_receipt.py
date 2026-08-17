from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from .enums import ConsentStatusEnum
from ..services import G2PRegisterDomainServiceConsentReceipt

class G2PConsentReceipt:

    related_consent_request_id: Mapped[str] = mapped_column(String, nullable=True)   # functional_record_id of the related consent request
    status: Mapped[ConsentStatusEnum] = mapped_column(String, nullable=True)     # ConsentStatusEnum
    attribute_list: Mapped[str] = mapped_column(Text, nullable=True)
    signature_algorithm: Mapped[str] = mapped_column(String, nullable=True)
    signature: Mapped[str] = mapped_column(Text, nullable=True)
    signed_at: Mapped[str] = mapped_column(DateTime, nullable=True)

# All Register classes should have the prefix G2PRegister
class G2PRegisterConsentReceipt(G2PRegister, G2PConsentReceipt):
    __tablename__ = "g2p_register_consent_receipts"

    def get_search_text_fields(self) -> str:
        """Return consent-receipt fields used to build search_text."""
        return G2PRegisterDomainServiceConsentReceipt().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return consent-receipt record_name from domain service implementation."""
        return G2PRegisterDomainServiceConsentReceipt().construct_record_name(self.to_dict())

# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryConsentReceipt(G2PRegisterHistory, G2PConsentReceipt):
    __tablename__ = "g2p_register_history_consent_receipts"

# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormConsentReceipt(G2PIntakeForm, G2PRegister, G2PConsentReceipt):
    __tablename__ = "g2p_intake_form_consent_receipts"

    def get_search_text_fields(self) -> str:
        """Return consent-receipt fields used to build search_text."""
        return G2PRegisterDomainServiceConsentReceipt().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return consent-receipt record_name from domain service implementation."""
        return G2PRegisterDomainServiceConsentReceipt().construct_record_name(self.to_dict())
