from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from .enums import IdTypeEnum, IdStatusEnum
from ..services import G2PRegisterDomainServiceRegId

class G2PRegId:

    id_type: Mapped[IdTypeEnum] = mapped_column(String, nullable=True)     # IdTypeEnum
    value: Mapped[str] = mapped_column(String, nullable=True)
    expiry_date: Mapped[str] = mapped_column(Date, nullable=True)
    status: Mapped[IdStatusEnum] = mapped_column(String, nullable=True)    # IdStatusEnum
    description: Mapped[str] = mapped_column(String, nullable=True)

# All Register classes should have the prefix G2PRegister
class G2PRegisterRegId(G2PRegister, G2PRegId):
    __tablename__ = "g2p_register_reg_ids"

    def get_search_text_fields(self) -> str:
        """Return reg-id fields used to build search_text."""
        return G2PRegisterDomainServiceRegId().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return reg-id record_name from domain service implementation."""
        return G2PRegisterDomainServiceRegId().construct_record_name(self.to_dict())

# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryRegId(G2PRegisterHistory, G2PRegId):
    __tablename__ = "g2p_register_history_reg_ids"

# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormRegId(G2PIntakeForm, G2PRegister, G2PRegId):
    __tablename__ = "g2p_intake_form_reg_ids"

    def get_search_text_fields(self) -> str:
        """Return reg-id fields used to build search_text."""
        return G2PRegisterDomainServiceRegId().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return reg-id record_name from domain service implementation."""
        return G2PRegisterDomainServiceRegId().construct_record_name(self.to_dict())
