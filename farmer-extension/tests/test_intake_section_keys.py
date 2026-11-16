"""Every section key the file import and the ODK intake send must be a section of the Farmer intake form.

The platform ingests a payload key only when it names one of the form's sections; any other key is dropped without an
error. The household members once went out as "hh_members", a name the form no longer has, so every imported or ODK
household lost its head and could not be submitted ("Household members must be entered"). The form's sections are the
farmer_intake__<section_id> tab sections the seed declares (meta_data/zz-oan/20_layout.sql).
"""
import ast
import json
import re
from pathlib import Path

from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1] / "src" / "openg2p_registry_farmer_extension"
MEMBERS = "household_household_household_member_section_02"


def form_sections():
    found = set()
    for path in (ROOT / "meta_data").rglob("*.sql"):
        found |= set(re.findall(r"farmer_intake__([a-z0-9_]+)", path.read_text(encoding="utf-8")))
    return found


def odk_sections():
    tree = ast.parse((ROOT / "odk" / "transform.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "SECTIONS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("odk/transform.py defines no SECTIONS")


def import_sections():
    text = (ROOT / "templates" / "farmer_file_import_intake.j2").read_text(encoding="utf-8")
    row = {"first_name": "Sample", "last_name": "Farmer", "gender": "FEMALE", "is_household_head": "yes"}
    return json.loads(Environment().from_string(text).render(expanded=row))


def test_seed_declares_the_members_section():
    assert MEMBERS in form_sections()


def test_odk_sends_only_form_sections():
    assert set(odk_sections()) - form_sections() == set()


def test_file_import_sends_only_form_sections():
    assert set(import_sections()) - form_sections() == set()


def test_imported_head_is_in_the_members_section():
    members = import_sections()[MEMBERS]
    assert len(members) == 1 and members[0]["is_head"] is True
