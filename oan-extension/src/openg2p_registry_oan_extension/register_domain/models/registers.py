"""OAN's own child register of the farmer, laid out as the farmer extension's.

FarmerPhone is a TABLE register under the Farmer (meta_data/05_registers.sql):
a farmer has any number of phone numbers. On the intake form a row is linked to
the farmer of the same submission. The farmer's identifiers are attributes of
the farmer itself (fields.py), not a table.
"""

from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from openg2p_registry_farmer_extension.register_domain.models.farmer import (
    G2PIntakeFormFarmer,
)
from sqlalchemy import Boolean, String, select
from sqlalchemy.orm import Mapped, mapped_column

from ..services import G2PRegisterDomainServiceFarmerPhone


async def _link_to_submission_farmer(row, session) -> None:
    result = await session.execute(
        select(G2PIntakeFormFarmer).where(G2PIntakeFormFarmer.submission_id == row.submission_id)
    )
    farmer = result.scalars().first()
    if farmer:
        row.link_internal_record_id = farmer.internal_record_id


class G2PFarmerPhone:
    phone_type: Mapped[str] = mapped_column(String, nullable=True)  # PRIMARY, SECONDARY, OTHER
    phone_number: Mapped[str] = mapped_column(String, nullable=True)  # national number
    country_code: Mapped[str] = mapped_column(String, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=True)
    phone_e164: Mapped[str] = mapped_column(String, nullable=True)  # derived


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

    async def get_link_internal_record_id(self, session):
        await _link_to_submission_farmer(self, session)

    def get_search_text_fields(self) -> str:
        return G2PRegisterDomainServiceFarmerPhone().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        return G2PRegisterDomainServiceFarmerPhone().construct_record_name(self.to_dict())
