# Everything the farmer extension provides, then OAN's additions below. Core
# resolves classes by name on this module, so a name defined here wins.

from datetime import datetime

from openg2p_registry_farmer_extension.openg2p_farmer.register_domain import schemas as _farmer
from openg2p_registry_farmer_extension.openg2p_farmer.register_domain.schemas import *

from ..fields import OAN_FIELDS
from .farmer_phone import (  # noqa: F401  re-exported for core
    G2PIntakeFormSchemaFarmerPhone,
    G2PRegisterHistorySchemaFarmerPhone,
    G2PRegisterSchemaFarmerPhone,
)


def _with_oan_fields(name: str, fields: dict) -> type:
    """The farmer schema of that name, plus the OAN fields as optional."""
    base = getattr(_farmer, name)
    annotations = {field: py_type | None for field, (_, py_type) in fields.items()}
    namespace = {"__annotations__": annotations, "__module__": __name__, **{f: None for f in fields}}
    return type(name, (base,), namespace)


# The history schemas are left as the farmer extension has them: upstream does
# not carry domain fields there either.
for _mnemonic, _fields in OAN_FIELDS.items():
    for _prefix in ("G2PRegisterSchema", "G2PIntakeFormSchema"):
        globals()[f"{_prefix}{_mnemonic}"] = _with_oan_fields(f"{_prefix}{_mnemonic}", _fields)

# The outcome of the Fayda verification that core's registrant authentication
# mixin keeps on the farmer's record (models/), shown by the id-authentication
# widget. Not the token: it is eSignet's subject, kept server-side.
AUTHENTICATION_FIELDS: dict[str, type] = {
    "last_authentication_id": str,
    "last_authentication_status": str,
    "last_authenticated_at": datetime,
    "authentication_expiry_at": datetime,
}
globals()["G2PRegisterSchemaFarmer"] = type(
    "G2PRegisterSchemaFarmer", (globals()["G2PRegisterSchemaFarmer"],),
    {"__annotations__": {f: t | None for f, t in AUTHENTICATION_FIELDS.items()},
     "__module__": __name__, **{f: None for f in AUTHENTICATION_FIELDS}})
