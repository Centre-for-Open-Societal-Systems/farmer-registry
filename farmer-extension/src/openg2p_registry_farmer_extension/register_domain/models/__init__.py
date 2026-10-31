# Everything the farmer extension provides, then OAN's additions below. Core
# resolves classes by name on this module, so a name defined here wins.
import logging

from openg2p_registry_core.models import G2PRegisterAuthentication
from openg2p_registry_core.models.g2p_register import _populate_record_name, _populate_search_text
from openg2p_registry_farmer_extension.openg2p_farmer.register_domain import models as _farmer
from openg2p_registry_farmer_extension.openg2p_farmer.register_domain.models import *
from sqlalchemy import event
from sqlalchemy.orm import column_property, mapped_column

from ..derived import farmer_search_text
from ..fields import OAN_FIELDS
from ..record_names import readable_name
from .farmer_phone import (  # noqa: F401  re-exported for core
    G2PIntakeFormFarmerPhone,
    G2PRegisterFarmerPhone,
    G2PRegisterHistoryFarmerPhone,
)


_logger = logging.getLogger("oan-record-names")


def _add_oan_columns() -> None:
    """Append each OAN field to the register, history and intake classes."""
    for mnemonic, fields in OAN_FIELDS.items():
        for prefix in ("G2PRegister", "G2PRegisterHistory", "G2PIntakeForm"):
            cls = getattr(_farmer, f"{prefix}{mnemonic}")
            for name, (column_type, _) in fields.items():
                if name not in cls.__table__.c:  # importing twice must not add twice
                    setattr(cls, name, mapped_column(column_type, nullable=True))


_add_oan_columns()


class G2PRegisterFarmer(_farmer.G2PRegisterFarmer, G2PRegisterAuthentication):
    """Registered OAN model subclass on the native Farmer table.

    Core's registrant authentication mixin puts the outcome of a Fayda
    (eSignet) verification on the record (last_authentication_status,
    last_authenticated_at, authentication_expiry_at): core writes them when the
    sign-in completes, only for a register whose model carries the mixin, and
    the id-authentication widget shows them (18_identity_verification.sql).
    """

    def get_search_text_fields(self) -> str:
        return farmer_search_text(self.to_dict())


def _map_authentication_columns_on_native_class() -> None:
    """Let the native farmer class read the mixin's columns too.

    The subclass puts the mixin's columns on the shared Farmer table, but the
    farmer extension's own code (household roster, post-ingest) loads rows
    through its native class, whose to_dict walks every table column. Map the
    same columns on that class so a native instance carries them as well.
    """
    native = _farmer.G2PRegisterFarmer
    mapper = native.__mapper__
    for name in G2PRegisterFarmer.__mapper__.c.keys():
        if name in mapper.c or name not in native.__table__.c:
            continue
        mapper.add_property(name, column_property(native.__table__.c[name]))


_map_authentication_columns_on_native_class()


class G2PIntakeFormFarmer(_farmer.G2PIntakeFormFarmer):
    """Intake discovery resolves this exported subclass by its native name."""

    def get_search_text_fields(self) -> str:
        return farmer_search_text(self.to_dict())


def _populate_derived_columns(mapper, connection, target) -> None:
    _populate_search_text(target)
    _populate_record_name(target)


def _listen_like_core(cls) -> None:
    """Fill search_text and record_name for a subclass on a native table.

    Core registers these listeners only on the class that declares the table,
    and without propagate, so rows saved through an OAN subclass would keep
    both columns NULL, and the register list (search_text ILIKE) would never
    show them. Core's helpers walk the MRO, so the OAN, farmer and core field
    hooks all contribute, exactly as for a native row.
    """
    for event_name in ("before_insert", "before_update"):
        if not event.contains(cls, event_name, _populate_derived_columns):  # importing twice must not add twice
            event.listen(cls, event_name, _populate_derived_columns)


for _cls in (G2PRegisterFarmer, G2PIntakeFormFarmer):
    if "__tablename__" not in _cls.__dict__:
        _listen_like_core(_cls)

# Registers whose upstream record name is the row's raw codes (or, for Farmer,
# leaves out the father's name).
READABLE_NAME_REGISTERS = ("Farmer", "Land", "Crop", "Livestock", "MembershipDetails", "FarmInputs")


def _readable_name_interceptor(mnemonic: str, intake: bool):
    def intercept(target, value, old, initiator):
        """Hand back the readable name whatever the name being set.

        Core joins what every class in the MRO returns from get_record_name_fields
        and sets record_name from its own before_insert/before_update listeners,
        which it registers when mappers are configured (after this module is
        imported). A listener of ours on those events could therefore run before
        core's and be overwritten, and a subclass cannot replace the upstream
        name. Intercepting the value as it is set does not depend on that order,
        and keeps core's name for a row that names nothing.
        """
        try:
            return readable_name(mnemonic, target.to_dict(), value, intake)
        except Exception as error:  # an unloaded attribute must never fail a save
            _logger.warning("Keeping the record name of %s %s: %s", type(target).__name__,
                            getattr(target, "__dict__", {}).get("internal_record_id"), error)
            return value

    return intercept


for _mnemonic in READABLE_NAME_REGISTERS:
    for _prefix in ("G2PRegister", "G2PIntakeForm"):
        event.listen(
            getattr(_farmer, f"{_prefix}{_mnemonic}").record_name,
            "set",
            _readable_name_interceptor(_mnemonic, _prefix == "G2PIntakeForm"),
            retval=True,
            propagate=True,
        )
