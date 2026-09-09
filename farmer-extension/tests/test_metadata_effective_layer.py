"""Guards the register-metadata seed against the silent-override trap.

db-seed (``registry-platform/docker/db-seed/entrypoint.sh``) loads every ``*.sql``
in ``find ... | sort`` order, so ``zz_*_layout.sql`` runs after
``g2p_register_sections.sql`` and its ``UPDATE ... SET section_ui_schema``
replaces that section's schema wholesale.

Validation added only to the base file for an overridden section therefore never
reaches the rendered form. That is not hypothetical: commit 83b4a46 added nine
name patterns and two required flags to
``farmer_farmer_personal_identification_section_01`` in the base file alone, and
every one of them was discarded on a clean seed.

These tests reconstruct the effective schema the way the seed does, then assert
the Gen1-parity ruleset signed off on G2R-26 against it.
"""

import json
import re
import unittest
from pathlib import Path

META = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "openg2p_registry_farmer_extension"
    / "meta_data"
    / "register-metadata"
)

PERSONAL = "farmer_farmer_personal_identification_section_01"
PHONE = "farmer_farmer_phone_numbers_section_01"
REG_IDS = "farmer_farmer_reg_ids_section_01"

NAME_FIELDS = [
    "first_name",
    "middle_name",
    "last_name",
    "first_name_amh",
    "middle_name_amh",
    "last_name_amh",
    "first_name_om",
    "middle_name_om",
    "last_name_om",
]

# Gen1 parity (G2R-26 sign-off): first name and father's name only. last_name
# holds the grandfather's name at 26% Gen1 fill, birth_date 10%, phone 13% --
# requiring any of those would make most real Gen1 records impossible to save.
REQUIRED_FIELDS = {"first_name", "middle_name"}


def _widgets(node, acc):
    if isinstance(node, dict):
        key = node.get("widget-id") or node.get("column-key")
        if key:
            acc[key] = node
        for value in node.values():
            _widgets(value, acc)
    elif isinstance(node, list):
        for value in node:
            _widgets(value, acc)
    return acc


def _base_sections():
    """section_id -> schema, from the multi-row INSERT in g2p_register_sections.sql."""
    text = (META / "g2p_register_sections.sql").read_text(encoding="utf-8")
    out = {}
    for match in re.finditer(
        r"\n\('[0-9a-f-]+','([a-z0-9_]+)',.*?'(\{\"panels\".*?)'(?=\s*,)",
        text,
        re.DOTALL,
    ):
        # single-quoted SQL literal: '' is one apostrophe
        out[match.group(1)] = json.loads(match.group(2).replace("''", "'"))
    return out


def _override_sections():
    """section_id -> (schema, filename) from the zz_*.sql files, in seed order.

    Two shapes carry a schema: an UPDATE that names the section in its WHERE
    clause (section_id *after* the body) and an INSERT that defines a section
    outright, as the phone sub-register does (section_id *before* the body).
    """
    out = {}
    for path in sorted(META.glob("zz_*.sql")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"SET\s+\"?section_ui_schema\"?\s*=\s*\$schema\$(.*?)\$schema\$"
            r".*?WHERE\s+\"?section_id\"?\s*=\s*'([a-z0-9_]+)'",
            text,
            re.DOTALL,
        ):
            out[match.group(2)] = (json.loads(match.group(1).strip()), path.name)
        for match in re.finditer(
            r"INSERT\s+INTO\s+[\"a-z_.]*g2p_register_sections\b.*?VALUES\s*\("
            r"\s*'[^']*',\s*'([a-z0-9_]+)'.*?\$schema\$(.*?)\$schema\$",
            text,
            re.DOTALL,
        ):
            out.setdefault(
                match.group(1), (json.loads(match.group(2).strip()), path.name)
            )
    return out


def effective_widgets(section_id):
    """The widgets the staff UI actually renders, after seed-order overrides."""
    override = _override_sections().get(section_id)
    schema = override[0] if override else _base_sections()[section_id]
    return _widgets(schema, {})


class TestEffectiveLayer(unittest.TestCase):
    def test_every_seed_file_is_parseable(self):
        """A malformed escape makes psql store nothing and the form render empty."""
        self.assertTrue(_base_sections(), "no base sections parsed")
        self.assertTrue(_override_sections(), "no override sections parsed")

    def test_personal_section_is_overridden(self):
        """If this stops holding, the guards below are testing the wrong layer."""
        self.assertIn(PERSONAL, _override_sections())

    def test_name_patterns_reach_the_rendered_form(self):
        widgets = effective_widgets(PERSONAL)
        for field in NAME_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, widgets)
                validation = widgets[field].get("widget-data-validation")
                self.assertIsNotNone(
                    validation, f"{field} has no validation in the effective layer"
                )
                self.assertIn("pattern", validation)

    def test_name_pattern_accepts_ethiopic(self):
        """The platform reference regex covers Latin and Devanagari only, and
        silently rejects Amharic and Oromo -- the whole point of the local range."""
        pattern = effective_widgets(PERSONAL)["first_name"]["widget-data-validation"][
            "pattern"
        ]
        matcher = re.compile(pattern)
        for good in ("አበበ", "Abebe", "Guyyaa", "O'Brien", "Bekele-Tadesse"):
            self.assertTrue(matcher.match(good), f"rejected valid name {good!r}")
        for bad in ("", "123", "@bebe"):
            self.assertFalse(matcher.match(bad), f"accepted invalid name {bad!r}")

    def test_required_flags_match_gen1_parity(self):
        widgets = effective_widgets(PERSONAL)
        for field in NAME_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(
                    widgets[field].get("widget-required") is True,
                    field in REQUIRED_FIELDS,
                )

    def test_phone_is_optional_and_local_format(self):
        """Gen1 fill is 13%, so parity means optional -- but when supplied it is
        the national part only, because Gen2 holds the country in its own column."""
        phone = effective_widgets(PHONE)["phone_number"]
        self.assertFalse(phone.get("widget-required", False))
        matcher = re.compile(phone["widget-data-validation"]["pattern"])
        for good in ("0912345678", "912345678", "0111234567"):
            self.assertTrue(matcher.match(good), f"rejected {good!r}")
        for bad in ("+251912345678", "251912345678", "091234567", "abcdefghij"):
            self.assertFalse(matcher.match(bad), f"accepted {bad!r}")

    def test_id_type_offers_exactly_gen1s_four_types(self):
        """Gen1's g2p_id_type table holds four rows and no more. FIN and FAN are
        not among them -- and neither is an IdTypeEnum member either, so the
        original dropdown offered two options the Pydantic schema would reject
        outright (G2R-26 Q5)."""
        options = effective_widgets(REG_IDS)["id_type"]["widget-data-source"]["options"]
        values = {option["value"] for option in options}
        self.assertEqual(
            values,
            {"UID", "RID", "FARMER_ODK_ACK_ID", "MEMBER_ODK_ACK_ID"},
        )

    def test_every_id_type_option_is_an_enum_member(self):
        """id_type is typed Optional[IdTypeEnum] on the schema, so an option
        outside the enum cannot be saved however good it looks in the form."""
        enums = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "openg2p_registry_farmer_extension"
            / "register_domain"
            / "models"
            / "enums.py"
        ).read_text(encoding="utf-8")
        block = enums.split("class IdTypeEnum")[1].split("class ")[0]
        members = set(re.findall(r'^\s+\w+ = "([A-Z_]+)"', block, re.MULTILINE))
        options = effective_widgets(REG_IDS)["id_type"]["widget-data-source"]["options"]
        for option in options:
            with self.subTest(option=option["value"]):
                self.assertIn(option["value"], members)

    def test_base_and_override_do_not_disagree_on_validation(self):
        """Both layers may carry a widget, but they must not carry different rules
        for it -- that drift is what this file exists to catch."""
        base = _widgets(_base_sections()[PERSONAL], {})
        effective = effective_widgets(PERSONAL)
        for field in NAME_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(
                    base[field].get("widget-data-validation", {}).get("pattern"),
                    effective[field].get("widget-data-validation", {}).get("pattern"),
                    f"{field}: base and override layers carry different patterns",
                )
                self.assertEqual(
                    base[field].get("widget-required") is True,
                    effective[field].get("widget-required") is True,
                    f"{field}: base and override layers disagree on required",
                )


if __name__ == "__main__":
    unittest.main()
