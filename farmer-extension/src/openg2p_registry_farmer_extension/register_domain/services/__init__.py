# Everything the farmer extension provides, then OAN's additions below. Core
# resolves classes by name on this module, so a name defined here wins.
import asyncio
import json
import time

from openg2p_fastapi_common.context import dbengine
from openg2p_registry_core.errors import G2PRegistryErrorCodes, G2PRegistryException
from openg2p_registry_core.services import G2PRegisterDomainService
from openg2p_registry_farmer_extension.openg2p_farmer.register_domain import services as _farmer
from openg2p_registry_farmer_extension.openg2p_farmer.register_domain.services import *
from openg2p_registry_farmer_extension.openg2p_farmer.register_domain.services.domain_validation_utils import (
    validation_error,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..record_names import compose
from .coded_values import coded_value_problems
from .derivations import DERIVATIONS, Derivations
from .domain_bounds import check_domain_bounds
from .household_intake import install_farmer_household_check  # noqa: F401
from .registrant_auth_compat import install_registrant_auth_compat  # noqa: F401
from .farmer_phone import FarmerPhoneService
from .upstream_messages import reword
from .widget_rules import Rules, _Say, check_record, collect_rules, normalize_record

# Section metadata is seed data that can change without a restart.
_RULES_TTL_SECONDS = 300
_cache: dict = {"at": None, "rules": {}, "registers": {}, "messages": {}}
_lock = asyncio.Lock()


def _json(value):
    # Raw SQL through asyncpg returns json and jsonb columns as text.
    return json.loads(value) if isinstance(value, str) else value


async def _load() -> tuple[Rules, dict[str, str], dict[str, str]]:
    # An empty cache is never fresh, including during the first five minutes
    # of machine uptime when monotonic() itself can be smaller than the TTL.
    if _cache["at"] is not None and time.monotonic() - _cache["at"] < _RULES_TTL_SECONDS:
        return _cache["rules"], _cache["registers"], _cache["messages"]
    async with _lock:
        if _cache["at"] is None or time.monotonic() - _cache["at"] >= _RULES_TTL_SECONDS:
            async with async_sessionmaker(dbengine.get())() as session:
                sections = (await session.execute(text(
                    "SELECT section_register_id, section_ui_schema FROM g2p_register_sections"))).all()
                registers = (await session.execute(text(
                    "SELECT register_mnemonic, register_id FROM g2p_register_definitions"))).all()
                messages = (await session.execute(text(
                    "SELECT domain_translation FROM registry_languages WHERE is_default"))).scalar()
            _cache.update(
                at=time.monotonic(),
                rules=collect_rules((r[0], _json(r[1])) for r in sections),
                registers={r[0]: r[1] for r in registers},
                messages=_json(messages) or {},
            )
    return _cache["rules"], _cache["registers"], _cache["messages"]


class _reworded:
    """Rewords a validation message raised inside it (upstream_messages)."""

    def __init__(self, messages: dict[str, str]):
        self.messages = messages

    async def __aenter__(self):
        return self

    async def __aexit__(self, kind, error, trace):
        if not (isinstance(error, G2PRegistryException) and error.message):
            return False
        if error.code == G2PRegistryErrorCodes.REQUEST_VALIDATION_ERROR.value[1]:
            validation_error(reword(error.message, self.messages))
        elif error.code == G2PRegistryErrorCodes.INVALID_REQUEST.value[1]:
            # Core's parent-link errors (an unknown household): reworded
            # only when this module knows the message, otherwise unchanged.
            plain = reword(error.message, self.messages)
            if plain != error.message:
                raise G2PRegistryException(code=error.code, message=plain) from error
        return False


class WidgetRuleValidation:
    """Adds the derived values and the section widgets' value rules to a
    register's domain checks: derive first, so the farmer checks see them.
    A message from the farmer extension's checks is reworded to name the field
    by its label and say what to enter (upstream_messages)."""

    _derive_first = False
    _checks_fayda_id = False
    _checks_master_data = False

    async def validate_domain_attributes(self, records: list[dict]):
        rules, registers, messages = await _load()
        if type(self)._derive_first:
            await self.derive(records)
        if type(self)._upstream_validates:
            from .intake_context import validation_records

            checked_records = await validation_records(records, self.register_mnemonic())
            async with _reworded(messages):
                await super().validate_domain_attributes(checked_records)
        field_rules = rules.get(registers.get(self.register_mnemonic()), {})
        problems: list[str] = []
        if field_rules:
            for record in records:
                normalize_record(record, field_rules)
            problems = [p for record in records for p in check_record(record, field_rules, messages)]
        say = _Say(messages)
        problems += check_domain_bounds(records, self.register_mnemonic(), field_rules, say)
        if type(self)._checks_master_data:
            # Gender, language and marital status against their Master Data
            # lists, the location against Master Data's, and a Fayda ID for
            # "Has national ID: Yes" (coded_values.py).
            problems += await coded_value_problems(records, say)
        if not problems and type(self)._checks_fayda_id:
            # The same Fayda ID on another farmer (form_integrity.py), said
            # by the field's label instead of the table's unique constraint.
            from .form_integrity import check_fayda_id_unique

            label = say.label(field_rules.get("foundational_id", {}).get("label"), "foundational_id")
            async with async_sessionmaker(dbengine.get())() as session:
                for record in records:
                    held = await check_fayda_id_unique(record, label, session, messages)
                    if held:
                        problems.append(held)
        if problems:
            validation_error("; ".join(dict.fromkeys(problems)))

    async def validate_intake_parent_link(self, record, link_internal_record_id, session):
        # Upstream's roster checks (the members against the household) run here.
        _, _, messages = await _load()
        async with _reworded(messages):
            await super().validate_intake_parent_link(record, link_internal_record_id, session)


_PREFIX = "G2PRegisterDomainService"


class ReadableRecordName:
    """The record name composed from the row's own values (record_names.py);
    the farmer extension's name stays the fallback for a row naming nothing."""

    def construct_record_name(self, payload: dict, extra: list[str] | None = None) -> str:
        name = compose(self.register_mnemonic(), payload)
        if not name:
            return super().construct_record_name(payload, extra)
        return " ".join([*(str(item).strip() for item in extra or [] if str(item).strip()), name])


def _with_widget_rules(name: str, base: type) -> type:
    upstream = base.validate_domain_attributes is not G2PRegisterDomainService.validate_domain_attributes
    derivations = DERIVATIONS.get(name[len(_PREFIX):], Derivations)
    return type(name, (ReadableRecordName, WidgetRuleValidation, derivations, base),
                {"__module__": __name__, "_upstream_validates": upstream, "_derive_first": True,
                 "_checks_fayda_id": name == _PREFIX + "Farmer",
                 "_checks_master_data": name == _PREFIX + "Farmer"})


# One subclass per farmer domain service, under the same name, so every
# register, including one the farmer extension adds later, gets the rules.
for _name in dir(_farmer):
    _base = getattr(_farmer, _name)
    if (
        _name.startswith(_PREFIX)
        and isinstance(_base, type)
        and issubclass(_base, G2PRegisterDomainService)
        and _base is not G2PRegisterDomainService
    ):
        globals()[_name] = _with_widget_rules(_name, _base)

# The registers this package adds.
for _name, _service in (("FarmerPhone", FarmerPhoneService),):
    globals()[_PREFIX + _name] = type(_PREFIX + _name, (WidgetRuleValidation, _service),
                                      {"__module__": __name__, "_upstream_validates": True})
