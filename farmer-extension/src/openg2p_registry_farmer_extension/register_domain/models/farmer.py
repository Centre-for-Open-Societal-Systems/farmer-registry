from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from sqlalchemy import Boolean, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_registry_core.models import (
    G2PRegister, G2PRegisterHistory, G2PGeo, G2PPerson,
    G2PPersonHistory, G2PGeoHistory
)
from ..services import G2PRegisterDomainServiceFarmer
from .enums import DisabilityTypeEnum, DisabilitySeverityEnum, SourceOfIncomeEnum, EducationalLevelEnum

class G2PFarmer:

    estimated_age: Mapped[int] = mapped_column(Integer, nullable=True)
    has_personal_phone: Mapped[bool] = mapped_column(Boolean, nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=True)
    disability_type: Mapped[DisabilityTypeEnum] = mapped_column(String, nullable=True)       # DisabilityTypeEnum
    disability_severity: Mapped[DisabilitySeverityEnum] = mapped_column(String, nullable=True)   # DisabilitySeverityEnum
    source_of_income: Mapped[SourceOfIncomeEnum] = mapped_column(String, nullable=True)      # SourceOfIncomeEnum; use source_of_income_other when OTHERS (Excel)
    source_of_income_other: Mapped[str] = mapped_column(String, nullable=True)
    language_spoken: Mapped[str] = mapped_column(String, nullable=True)       # Attribute lookup (Excel: ISO-639-2 searchable dropdown)
    education_level: Mapped[EducationalLevelEnum] = mapped_column(String, nullable=True)       # EducationalLevelEnum
    national_id_masked: Mapped[str] = mapped_column(String, nullable=True)

    # Socio-Economic Data
    is_household_head: Mapped[bool] = mapped_column(Boolean, nullable=True)
    psnp_user: Mapped[bool] = mapped_column(Boolean, nullable=True)

    # Household Information
    number_of_males_in_the_family: Mapped[int] = mapped_column(Integer, nullable=True)
    father_included: Mapped[bool] = mapped_column(Boolean, nullable=True)
    number_of_females_in_the_family: Mapped[int] = mapped_column(Integer, nullable=True)
    mother_included: Mapped[bool] = mapped_column(Boolean, nullable=True)
    number_of_children_in_the_family: Mapped[int] = mapped_column(Integer, nullable=True)
    family_size: Mapped[int] = mapped_column(Integer, nullable=True)

    # Farmer Data
    is_farmer: Mapped[bool] = mapped_column(Boolean, nullable=True)
    primary_language: Mapped[str] = mapped_column(String, nullable=True)
    farming_type: Mapped[str] = mapped_column(String, nullable=True)


# All Register classes should have the prefix G2PRegister
class G2PRegisterFarmer(G2PRegister, G2PPerson, G2PGeo, G2PFarmer):
    __tablename__ = "g2p_register_farmers"

    @property
    def email(self) -> str | None:
        """Alias property to return email from emails list to satisfy section ui schema."""
        if self.emails and isinstance(self.emails, list) and len(self.emails) > 0:
            return self.emails[0]
        return None

    @email.setter
    def email(self, value: str | None) -> None:
        if value:
            self.emails = [value]
        else:
            self.emails = []

    @property
    def personal_phone_number(self) -> bool | None:
        """Alias property to return has_personal_phone to satisfy section ui schema."""
        return self.has_personal_phone

    @personal_phone_number.setter
    def personal_phone_number(self, value: bool | None) -> None:
        self.has_personal_phone = value


    def get_record_name_fields(self) -> str:
        """Return farmer fields used to build record_name."""
        return G2PRegisterDomainServiceFarmer().construct_record_name(self.to_dict())

    def get_search_text_fields(self) -> str:
        """Return farmer fields used to build search_text."""
        return G2PRegisterDomainServiceFarmer().construct_search_text(self.to_dict())

# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryFarmer(G2PRegisterHistory, G2PPersonHistory, G2PGeoHistory, G2PFarmer):
    __tablename__ = "g2p_register_history_farmers"

    @property
    def email(self) -> str | None:
        """Alias property to return email from emails list to satisfy section ui schema."""
        if self.emails and isinstance(self.emails, list) and len(self.emails) > 0:
            return self.emails[0]
        return None

    @email.setter
    def email(self, value: str | None) -> None:
        if value:
            self.emails = [value]
        else:
            self.emails = []

    @property
    def personal_phone_number(self) -> bool | None:
        """Alias property to return has_personal_phone to satisfy section ui schema."""
        return self.has_personal_phone

    @personal_phone_number.setter
    def personal_phone_number(self, value: bool | None) -> None:
        self.has_personal_phone = value


# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormFarmer(G2PIntakeForm, G2PRegister, G2PPerson, G2PGeo, G2PFarmer):
    __tablename__ = "g2p_intake_form_farmers"

    @property
    def email(self) -> str | None:
        """Alias property to return email from emails list to satisfy section ui schema."""
        if self.emails and isinstance(self.emails, list) and len(self.emails) > 0:
            return self.emails[0]
        return None

    @email.setter
    def email(self, value: str | None) -> None:
        if value:
            self.emails = [value]
        else:
            self.emails = []

    @property
    def personal_phone_number(self) -> bool | None:
        """Alias property to return has_personal_phone to satisfy section ui schema."""
        return self.has_personal_phone

    @personal_phone_number.setter
    def personal_phone_number(self, value: bool | None) -> None:
        self.has_personal_phone = value


    def get_record_name_fields(self) -> str:
        """Return farmer fields used to build record_name."""
        return G2PRegisterDomainServiceFarmer().construct_record_name(self.to_dict())

    def get_search_text_fields(self) -> str:
        """Return farmer fields used to build search_text."""
        return G2PRegisterDomainServiceFarmer().construct_search_text(self.to_dict())
