"""The household head listed in the member roster is counted once.

Runs the real upstream household_roster.py (loaded under its package name with
the platform pieces it imports stubbed) with OAN's wrapper installed, so no
platform image is needed.
"""

import enum
import importlib.util
import sys
import types
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKG = "openg2p_registry_farmer_extension"
UPSTREAM_DIR = ROOT / "farmer-extension/src" / PKG / "openg2p_farmer/register_domain/services"
CHAIN = [
    f"{PKG}.openg2p_farmer",
    f"{PKG}.openg2p_farmer.register_domain",
    f"{PKG}.openg2p_farmer.register_domain.services",
    f"{PKG}.openg2p_farmer.register_domain.services.utils",
]
ROSTER = f"{PKG}.openg2p_farmer.register_domain.services.utils.household_roster"
STUBBED = CHAIN + [
    ROSTER,
    f"{CHAIN[2]}.domain_validation_utils",
    "openg2p_registry_core",
    "openg2p_registry_core.models",
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
]


def _module(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    return module


def _parse_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(value[:10]) if value else None


@pytest.fixture()
def roster(monkeypatch):
    class Gender(str, enum.Enum):
        MALE = "MALE"
        FEMALE = "FEMALE"

    class Status(str, enum.Enum):
        ACTIVE = "ACTIVE"

    class Action(str, enum.Enum):
        ADD = "ADD"

    stubs = {
        "openg2p_registry_core": _module("openg2p_registry_core", __path__=[]),
        "openg2p_registry_core.models": _module(
            "openg2p_registry_core.models",
            ChangeActionEnum=Action,
            GenderEnum=Gender,
            RecordStatusEnum=Status,
        ),
        "sqlalchemy": _module("sqlalchemy", select=lambda *a: None),
        "sqlalchemy.ext": _module("sqlalchemy.ext", __path__=[]),
        "sqlalchemy.ext.asyncio": _module("sqlalchemy.ext.asyncio", AsyncSession=object),
        f"{CHAIN[2]}.domain_validation_utils": _module(
            "domain_validation_utils",
            as_int=lambda v: None if v in (None, "") else int(v),
            parse_date=_parse_date,
        ),
    }
    for name in CHAIN:
        stubs[name] = _module(name, __path__=[])
    package = sys.modules.get(PKG) or __import__(PKG)
    for name in STUBBED:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, PKG, package)
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(ROSTER, UPSTREAM_DIR / "utils/household_roster.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, ROSTER, module)
    spec.loader.exec_module(module)
    sys.modules[CHAIN[3]].household_roster = module

    from openg2p_registry_farmer_extension import household_roster_head

    assert household_roster_head.install()
    assert household_roster_head.install()  # idempotent
    return module


def person(first, last, born, gender, **extra):
    return {
        "record_status": "ACTIVE",
        "first_name": first,
        "last_name": last,
        "birth_date": born,
        "gender": gender,
        **extra,
    }


def counts(roster, members, farmers, **kwargs):
    return roster.compute_household_roster_counts(roster.union_roster_people(members, farmers, **kwargs))


FIRST, LAST, BORN = "Yohannes", "Tadesse", "1981-02-08"


def farmer(**extra):
    return person(FIRST, LAST, BORN, "MALE", foundational_id="FID-1", is_household_head=True, **extra)


def head_row(**extra):
    return person(FIRST, LAST, BORN, "MALE", is_head=True, **extra)


def wife():
    return person("Selamawit", "Haile", "1985-11-23", "FEMALE", relationship_to_the_head="SPOUSE")


def daughter():
    return person("Hanna", "Yohannes", "2012-05-01", "FEMALE", relationship_to_the_head="CHILD")


def test_head_listed_in_roster_without_id_counts_once(roster):
    result = counts(roster, [head_row(), wife(), daughter()], [farmer()])
    assert (result.size_of_group, result.number_of_male_members, result.number_of_female_members) == (3, 1, 2)


def test_head_row_collapses_by_flag_even_if_spelled_differently(roster):
    head = person("Yohanes", "Tadese", None, "MALE", is_head=True)
    assert counts(roster, [head, wife()], [farmer()]).size_of_group == 2


def test_head_relationship_self_without_flag_collapses(roster):
    head = person("Someone", "Else", None, "MALE", relationship_to_the_head="SELF")
    assert counts(roster, [head, wife()], [farmer()]).size_of_group == 2


def test_head_listed_with_the_farmers_id_counts_once(roster):
    result = counts(roster, [head_row(foundational_id=" fid-1 "), wife()], [farmer()])
    assert result.size_of_group == 2 and result.number_of_male_members == 1


def test_member_who_is_a_non_head_farmer_matches_by_name_and_birth_date(roster):
    other = person(FIRST, LAST, BORN, "MALE", foundational_id="FID-1")
    member = person(FIRST, LAST, BORN, "MALE", relationship_to_the_head="SIBLING")
    assert counts(roster, [member, wife()], [other]).size_of_group == 2


def test_name_match_ignores_case_whitespace_apostrophes_and_unicode_form(roster):
    farmers = [person("Ze’ru", "  Geʼez  ", "1990-01-01", "MALE", foundational_id="F-9")]
    member = person("ZE'RU", "ge'ez", "1990-01-01T00:00:00", "MALE", relationship_to_the_head="SIBLING")
    assert counts(roster, [member], farmers).size_of_group == 1
    amharic = [person("ዮሐንስ", "ታደሰ", "1981-02-08", "MALE", foundational_id="F-8")]
    assert counts(roster, [person("ዮሐንስ ", " ታደሰ", "1981-02-08", "MALE")], amharic).size_of_group == 1


def test_same_name_different_birth_date_is_a_different_person(roster):
    namesake = person(FIRST, LAST, "1990-03-03", "MALE", relationship_to_the_head="SIBLING")
    result = counts(roster, [namesake, wife()], [farmer()])
    assert result.size_of_group == 3 and result.number_of_male_members == 2


def test_namesake_with_a_different_id_is_kept(roster):
    namesake = person(FIRST, LAST, BORN, "MALE", foundational_id="FID-2", relationship_to_the_head="SIBLING")
    assert counts(roster, [namesake, wife()], [farmer()]).size_of_group == 3


def test_a_missing_birth_date_never_merges_by_name(roster):
    member = person(FIRST, LAST, None, "MALE", relationship_to_the_head="SIBLING")
    assert counts(roster, [member], [farmer()]).size_of_group == 2


def test_inactive_farmer_does_not_absorb_the_member(roster):
    assert counts(roster, [head_row(), wife()], [farmer(record_status="INACTIVE")]).size_of_group == 2


def test_overlay_head_row_is_not_counted_again(roster):
    linked = head_row(link_internal_record_id="hh-1")
    result = counts(
        roster, [linked, wife()], [farmer()], overlay_person=linked, overlay_household_id="hh-1"
    )
    assert result.size_of_group == 2


def test_upstream_file_is_unchanged_from_the_published_copy():
    published = ROOT / "sample-farmer-extension/src" / PKG / "register_domain/services/utils/household_roster.py"
    assert (UPSTREAM_DIR / "utils/household_roster.py").read_text() == published.read_text()
