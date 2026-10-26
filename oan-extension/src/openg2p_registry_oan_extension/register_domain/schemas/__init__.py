# Everything the farmer extension provides, then OAN's additions below. Core
# resolves classes by name on this module, so a name defined here wins.

from openg2p_registry_farmer_extension.register_domain import schemas as _farmer
from openg2p_registry_farmer_extension.register_domain.schemas import *

from ..fields import OAN_FIELDS
from .registers import (  # noqa: F401  re-exported for core
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
