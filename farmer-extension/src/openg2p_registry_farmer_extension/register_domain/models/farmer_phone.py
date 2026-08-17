from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from ..services import G2PRegisterDomainServiceFarmerPhone
from .enums import PhoneTypeEnum


class G2PFarmerPhone:
    phone_type: Mapped[PhoneTypeEnum] = mapped_column(String, nullable=False)
    phone_number: Mapped[str] = mapped_column(String, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    country_code: Mapped[str] = mapped_column(String, nullable=True)  # matches g2p.phone.number's country_id in the ATI Odoo source


class G2PRegisterFarmerPhone(G2PRegister, G2PFarmerPhone):
    __tablename__ = "g2p_register_farmer_phones"

    def get_search_text_fields(self) -> str:
        return G2PRegisterDomainServiceFarmerPhone().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        return G2PRegisterDomainServiceFarmerPhone().construct_record_name(self.to_dict())


class G2PRegisterHistoryFarmerPhone(G2PRegisterHistory, G2PFarmerPhone):
    __tablename__ = "g2p_register_history_farmer_phones"


class G2PIntakeFormFarmerPhone(G2PIntakeForm, G2PRegister, G2PFarmerPhone):
    __tablename__ = "g2p_intake_form_farmer_phones"

    def get_search_text_fields(self) -> str:
        return G2PRegisterDomainServiceFarmerPhone().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        return G2PRegisterDomainServiceFarmerPhone().construct_record_name(self.to_dict())
