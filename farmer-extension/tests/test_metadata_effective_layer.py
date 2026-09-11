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
PHOTO = "farmer_farmer_photo_section_01"
# Also the scope of docker/staff-ui/assets/intake-photo-widget.css --
# HeaderSectionWidget derives its CSS class from this id.
PHOTO_WIDGET_ID = "farmer-photo"

FARMER_REGISTER = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"
FARMER_INTAKE_TAB = "a1a4d25a-1cd4-4356-abac-72482721"

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
    "father_first_name",
    "father_middle_name",
    "father_last_name",
]

# Gen1 parity (G2R-26 sign-off): the farmer's first name and the father's
# first name only; the father is his own first/middle/last triple, so the
# farmer's middle_name is optional. last_name holds the grandfather's name at
# 26% Gen1 fill, birth_date 10%, phone 13% -- requiring any of those would make
# most real Gen1 records impossible to save.
REQUIRED_FIELDS = {"first_name", "father_first_name"}

BIRTH = "farmer_farmer_birth_information_section_01"
SOCIO = "farmer_farmer_socio_economic_and_health_section_04"


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


# (tab_section_id, [register_id,] tab_id, section_id, section_order) -- the
# register table carries a register_id column the intake table does not.
_ROW_PATTERNS = {
    "g2p_register_ui_tab_sections": (
        r"\(\s*'[^']+'\s*,\s*'[^']+'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*\d+\s*\)"
    ),
    "g2p_intake_form_ui_tab_sections": (
        r"\(\s*'[^']+'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*\d+\s*\)"
    ),
}


def _tab_attachments(table):
    """(tab_id, section_id) pairs INSERTed into a *_ui_tab_sections table,
    across the base multi-row INSERT and the single-row INSERTs in zz_ files."""
    out = set()
    for path in sorted(META.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        for statement in re.split(r";\s*\n", text):
            if "INSERT" not in statement or table not in statement:
                continue
            body = statement.split("VALUES", 1)[-1]
            out.update(re.findall(_ROW_PATTERNS[table], body))
    return out


def effective_schema(section_id):
    """The section schema the staff UI actually renders, after seed-order
    overrides."""
    override = _override_sections().get(section_id)
    return override[0] if override else _base_sections()[section_id]


def effective_widgets(section_id):
    """The widgets the staff UI actually renders, after seed-order overrides."""
    return _widgets(effective_schema(section_id), {})


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

    def test_photo_capture_reaches_the_intake_form(self):
        """The intake form never renders the header section (whose picker is the
        only other photo entry point), so without a widget bound to the photo
        column staff cannot capture a farmer photo during intake at all -- the
        gap the photo section exists to close.

        It reuses header-section rather than the generic 'file' widget because
        that is the only registered widget with an image picker AND a preview:
        FileInputWidget shows the chosen file's name, not the photo."""
        photo = effective_widgets(PHOTO)[PHOTO_WIDGET_ID]
        self.assertEqual(photo.get("widget"), "header-section")
        self.assertEqual(
            photo.get("widget-data-path", {}).get("imageUrl"),
            # HeaderSectionWidget's picker serializes the pick into the
            # imageUrl path; _persist_embedded_profile_photo uploads it from
            # there and stores the document_id (test_farmer_photo_upload.py).
            f"{FARMER_REGISTER}.record_image_url",
        )

    def test_photo_widget_carries_no_header_only_paths(self):
        """Load-bearing, not cosmetic. HeaderSectionWidget renders its status
        <select> and status-reason <input> unconditionally, and in an editable
        section they are live controls. Omitting their widget-data-path keys is
        what stops the widget reading or writing them -- findValue() and
        updateFieldValue() both return early on a missing path. The stylesheet
        only hides what is left over."""
        paths = effective_widgets(PHOTO)[PHOTO_WIDGET_ID].get("widget-data-path", {})
        for key in (
            "status",
            "statusReason",
            "name",
            "functionalId",
            "createdBy",
            "createdAt",
            "lastApprovedBy",
            "lastApprovedAt",
            "completionScore",
            "idealScore",
        ):
            self.assertNotIn(
                key,
                paths,
                f"{key!r} is bound on the intake photo widget; the header "
                "section would render (and for status, write) it mid-intake",
            )

    def test_photo_section_is_editable(self):
        """buildEditableSection only forces widget-readonly=false when the
        section says section-editable. HeaderSectionWidget defaults to readonly
        ("widget-readonly !== false"), and a readonly one renders no
        Upload/Delete overlay -- an avatar with no way to set it."""
        self.assertIs(effective_schema(PHOTO).get("section-editable"), True)

    def test_photo_widget_id_matches_the_stylesheet_selector(self):
        """The stylesheet that trims the header-only rows is scoped by the
        class HeaderSectionWidget builds from this widget-id. Renaming one
        without the other silently restores the empty rows."""
        css = (
            Path(__file__).resolve().parents[2]
            / "docker"
            / "staff-ui"
            / "assets"
            / "intake-photo-widget.css"
        ).read_text(encoding="utf-8")
        selector = f".header-section-widget-{PHOTO_WIDGET_ID}"
        self.assertIn(f"{selector} .hdr-info", css)
        self.assertIn(f"{selector} .hdr-right", css)

    def test_photo_section_is_attached_to_the_intake_form(self):
        self.assertIn(
            (FARMER_INTAKE_TAB, PHOTO),
            _tab_attachments("g2p_intake_form_ui_tab_sections"),
        )

    def test_photo_is_captured_in_exactly_one_place_per_experience(self):
        """The register detail view already renders and edits the profile
        picture through the header section's own picker. A second control on
        the same tab -- which is what happened while this widget lived in
        Personal Information, a section attached to both tabs -- shows the
        farmer photo twice, two inputs writing one field."""
        personal = effective_widgets(PERSONAL)
        for widget_id in (PHOTO_WIDGET_ID, "record_image_document_id"):
            self.assertNotIn(
                widget_id,
                personal,
                "the photo widget is back in Personal Information, which the "
                "detail view renders alongside the header picker",
            )
        for tab_id, section_id in _tab_attachments("g2p_register_ui_tab_sections"):
            self.assertNotEqual(
                section_id,
                PHOTO,
                f"photo section attached to register tab {tab_id}; the header "
                "section already carries the picker there",
            )

    def test_required_flags_match_gen1_parity(self):
        widgets = effective_widgets(PERSONAL)
        for field in NAME_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(
                    widgets[field].get("widget-required") is True,
                    field in REQUIRED_FIELDS,
                )

    def test_gender_lives_in_birth_information(self):
        """Gen1 groups gender with the birth details. It used to sit on a row of
        its own under the name grid in Personal Information, reading as a stray
        field from another section."""
        self.assertIn("gender", effective_widgets(BIRTH))
        self.assertNotIn("gender", effective_widgets(PERSONAL))

    def test_gender_is_bound_to_the_farmer_column(self):
        gender = effective_widgets(BIRTH)["gender"]
        self.assertEqual(gender.get("widget-data-path"), f"{FARMER_REGISTER}.gender")

    def test_yes_no_flags_are_selects_not_checkboxes(self):
        """The checkbox widget captions itself with its current state ("No" while
        unchecked), so the caption reads as an answer staff can pick -- and
        clicking it flips the box to Yes. Yes/No questions are selects with
        boolean option values, which also keep a blank "not asked" state."""
        widgets = effective_widgets(SOCIO)
        for field in ("disabled", "is_psnp_user"):
            with self.subTest(field=field):
                widget = widgets[field]
                self.assertEqual(widget.get("widget"), "select")
                values = [
                    option["value"]
                    for option in widget["widget-data-source"]["options"]
                ]
                self.assertEqual(values, [True, False])

    def test_disability_details_are_gated_on_a_boolean(self):
        """The select hands back the option's original (boolean) value, so the
        show-conditions on the disability fields must compare against true,
        not the string "true"."""
        widgets = effective_widgets(SOCIO)
        for field in ("disability_type", "disability_severity"):
            with self.subTest(field=field):
                condition = widgets[field]["widget-data-options"]["condition"]
                self.assertEqual(condition["field"], f"{FARMER_REGISTER}.disabled")
                self.assertIs(condition["value"], True)

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
