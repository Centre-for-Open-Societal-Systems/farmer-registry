from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import Boolean, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Date, String, select
from openg2p_registry_core.models import (
    G2PRegister, G2PRegisterHistory, G2PGeo, G2PPerson,
    G2PPersonHistory, G2PGeoHistory
)
from ..services import G2PRegisterDomainServiceIds
from .enums import DisabilityTypeEnum, DisabilitySeverityEnum, SourceOfIncomeEnum, EducationalLevelEnum

class G2PIds:

    id_type: Mapped[str] = mapped_column(String, nullable=True)
    id_number: Mapped[str] = mapped_column(String, nullable=True)
    expiry_date: Mapped[Date] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(String, nullable=True)

# All Register classes should have the prefix G2PRegister
class G2PRegisterIds(G2PRegister, G2PPerson, G2PGeo, G2PIds):
    __tablename__ = "g2p_register_ids"

    def get_record_name_fields(self) -> str:
        """Return farmer fields used to build record_name."""
        return G2PRegisterDomainServiceIds().construct_record_name(self.to_dict())

    def get_search_text_fields(self) -> str:
        """Return farmer fields used to build search_text."""
        return G2PRegisterDomainServiceIds().construct_search_text(self.to_dict())

# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryIds(G2PRegisterHistory, G2PPersonHistory, G2PGeoHistory, G2PIds):
    __tablename__ = "g2p_register_history_ids"

# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormIds(G2PIntakeForm, G2PRegister, G2PPerson, G2PGeo, G2PIds):
    __tablename__ = "g2p_intake_form_ids"

    def get_record_name_fields(self) -> str:
        """Return farmer fields used to build record_name."""
        return G2PRegisterDomainServiceIds().construct_record_name(self.to_dict())

    def get_search_text_fields(self) -> str:
        """Return farmer fields used to build search_text."""
        return G2PRegisterDomainServiceIds().construct_search_text(self.to_dict())
