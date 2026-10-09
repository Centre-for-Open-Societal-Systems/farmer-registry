"""Keeps the server-side rules and the form's client-side rules identical.

``validation_rules.py`` restates the intake rules in Python because
``widget-data-validation`` is enforced by the browser alone. Two copies of a rule
drift, and both directions of drift are bad: a server stricter than the form
rejects a record the staff were told was fine, and a server looser than the form
lets bulk import write data the form would never have accepted.

So these tests read the actual seed SQL and compare it against the Python
constants, rather than restating either by hand.

Stdlib only, deliberately: it must run on a developer host without the platform
package or a database, which is where the drift gets introduced.
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "openg2p_registry_farmer_extension"
META = ROOT / "meta_data" / "register-metadata"
RULES_PATH = ROOT / "register_domain" / "services" / "validation_rules.py"

PERSONAL = "farmer_farmer_personal_identification_section_01"


def _load_rules():
    """Import validation_rules.py directly.

    Importing it as part of the package would pull in openg2p_registry_core via
    the services __init__, which is not installed on a plain host checkout. The
    module itself imports nothing but `re`, so loading it standalone is safe.
    """
    spec = importlib.util.spec_from_file_location("validation_rules", RULES_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = _load_rules()


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


def _schemas_in(filename):
    """Every section_ui_schema in a seed file, whichever way it is quoted."""
    text = (META / filename).read_text(encoding="utf-8")
    out = []
    for body in re.findall(r"\$schema\$(.*?)\$schema\$", text, re.DOTALL):
        out.append(json.loads(body.strip()))
    for match in re.finditer(r"'(\{\"panels\".*?)'(?=\s*,)", text, re.DOTALL):
        out.append(json.loads(match.group(1).replace("''", "'")))
    return out


def _find_widget(filename, widget_id):
    for schema in _schemas_in(filename):
        found = _widgets(schema, {})
        if widget_id in found:
            return found[widget_id]
    raise AssertionError(f"{widget_id} not found in {filename}")


class TestRulesMatchMetadata(unittest.TestCase):
    def test_name_pattern_matches_the_form(self):
        widget = _find_widget("zz_farmer_personal_socio_layout.sql", "first_name")
        self.assertEqual(
            widget["widget-data-validation"]["pattern"],
            rules.NAME_PATTERN,
            "server NAME_PATTERN has drifted from the intake form's pattern",
        )

    def test_name_max_length_matches_the_form(self):
        widget = _find_widget("zz_farmer_personal_socio_layout.sql", "first_name")
        self.assertEqual(
            widget["widget-data-validation"].get("maxLength"),
            rules.NAME_MAX_LENGTH,
        )

    def test_every_name_field_carries_the_same_rule(self):
        for field in rules.NAME_FIELDS:
            with self.subTest(field=field):
                widget = _find_widget("zz_farmer_personal_socio_layout.sql", field)
                self.assertEqual(
                    widget["widget-data-validation"]["pattern"], rules.NAME_PATTERN
                )

    def test_required_name_fields_match_the_form(self):
        for field in rules.NAME_FIELDS:
            with self.subTest(field=field):
                widget = _find_widget("zz_farmer_personal_socio_layout.sql", field)
                self.assertEqual(
                    widget.get("widget-required") is True,
                    field in rules.REQUIRED_NAME_FIELDS,
                )

    def test_phone_pattern_matches_the_form(self):
        widget = _find_widget("zz_farmer_phone_register.sql", "phone_number")
        self.assertEqual(
            widget["widget-data-validation"]["pattern"],
            rules.PHONE_PATTERN,
            "server PHONE_PATTERN has drifted from the intake form's pattern",
        )

    def test_national_id_pattern_matches_the_form(self):
        widget = _find_widget("g2p_register_sections.sql", "value")
        self.assertEqual(
            widget["widget-data-validation"]["pattern"],
            rules.NATIONAL_ID_PATTERN,
        )

    def test_every_offered_id_type_has_a_server_rule(self):
        """A type the form offers but the server has no opinion on is fine; a
        type in ID_TYPE_PATTERNS that the form does not offer is a leftover."""
        widget = _find_widget("g2p_register_sections.sql", "id_type")
        offered = {o["value"] for o in widget["widget-data-source"]["options"]}
        self.assertTrue(
            set(rules.ID_TYPE_PATTERNS) <= offered,
            f"server has rules for types the form does not offer: "
            f"{set(rules.ID_TYPE_PATTERNS) - offered}",
        )


class TestRuleBehaviour(unittest.TestCase):
    def test_names_accept_ethiopic_and_latin(self):
        for good in ("አበበ", "Abebe", "Guyyaa", "O'Brien", "Bekele-Tadesse"):
            self.assertTrue(rules.matches(rules.NAME_PATTERN, good), good)

    def test_names_reject_digits_and_symbols(self):
        for bad in ("123", "Abebe1", "@bebe", "<script>"):
            self.assertFalse(rules.matches(rules.NAME_PATTERN, bad), bad)

    def test_blank_is_not_a_format_error(self):
        """Emptiness is the required-check's business. Conflating the two shows
        'invalid format' on a field the user simply left alone."""
        for blank in (None, "", "   "):
            self.assertTrue(rules.matches(rules.NAME_PATTERN, blank))

    def test_phone_accepts_local_and_gen1_e164_forms(self):
        for good in ("0912345678", "912345678", "0111234567", "+251912345678", "251912345678"):
            self.assertTrue(rules.matches(rules.PHONE_PATTERN, good), good)
        for bad in ("091234567", "09123456789", "+25109123456", "+1912345678", "0012345678", "abcdefghij"):
            self.assertFalse(rules.matches(rules.PHONE_PATTERN, bad), bad)

    def test_phone_max_length_matches_the_form(self):
        widget = _find_widget("zz_farmer_phone_register.sql", "phone_number")
        self.assertEqual(widget["widget-data-validation"].get("maxLength"), rules.PHONE_MAX_LENGTH)
        self.assertEqual(len("+251912345678"), rules.PHONE_MAX_LENGTH)

    def test_every_accepted_form_normalises_to_the_national_number(self):
        for raw in (
            "0912345678",
            "912345678",
            "+251912345678",
            "251912345678",
            " +251 91-234-5678 ",
            "(091) 234 5678",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(rules.normalize_phone(raw), "912345678")
                self.assertEqual(rules.phone_e164(rules.normalize_phone(raw)), "+251912345678")

    def test_normalise_rejects_junk_and_blank(self):
        for raw in (None, "", "   ", "091234567", "+1912345678", "phone", "0912345678x"):
            with self.subTest(raw=raw):
                self.assertIsNone(rules.normalize_phone(raw))
        self.assertIsNone(rules.phone_e164(None))

    def test_national_id_allows_the_fan_prefix(self):
        for good in ("123456789012", "FAN-123456789012", "FAN-1234567890123456", "1" * 29):
            self.assertTrue(rules.matches(rules.NATIONAL_ID_PATTERN, good), good)
        for bad in ("12345678901", "12345678901234567", "AB-2024-0091", "FAN123456789012", "ET-NID-100001"):
            self.assertFalse(rules.matches(rules.NATIONAL_ID_PATTERN, bad), bad)

    def test_uid_and_rid_are_told_apart(self):
        """The form's column pattern is the union; the per-type rules
        are what keep a UID out of the RID slot and the reverse."""
        uid, rid = rules.ID_TYPE_PATTERNS["UID"], rules.ID_TYPE_PATTERNS["RID"]
        for fin_or_fan in ("123456789012", "1234567890123456", "FAN-1234567890123456"):
            self.assertTrue(rules.matches(uid, fin_or_fan), fin_or_fan)
            self.assertFalse(rules.matches(rid, fin_or_fan), fin_or_fan)
        self.assertTrue(rules.matches(rid, "1" * 29))
        self.assertFalse(rules.matches(uid, "1" * 29))

    def test_intake_rules_script_uses_the_same_id_patterns(self):
        """farmer-intake-rules.js restates UID/RID to explain a refused row on
        the spot; it must say exactly what the server will enforce."""
        script = (
            Path(__file__).resolve().parents[2] / "docker" / "staff-ui" / "assets" / "farmer-intake-rules.js"
        )
        if not script.exists():
            self.skipTest("staff-ui assets not mounted (run with the whole repo)")
        text = script.read_text(encoding="utf-8")
        for name in ("UID_PATTERN", "RID_PATTERN"):
            m = re.search(rf"var {name} = /(.+)/;", text)
            self.assertIsNotNone(m, f"{name} not found in farmer-intake-rules.js")
            self.assertEqual(m.group(1), getattr(rules, name), f"{name} drifted between JS and Python")

    def test_every_per_type_rule_is_within_the_form_pattern(self):
        """Anything a per-type rule accepts, the form must let through."""
        for sample in ("123456789012", "1234567890123456", "FAN-1234567890123456", "1" * 29):
            self.assertTrue(rules.matches(rules.NATIONAL_ID_PATTERN, sample), sample)

    def test_bulk_import_is_not_treated_as_interactive(self):
        """Required-checks must not fire on migrated records."""
        for source in ("IMPORT_FILE", "PARTNER", "VERIFIABLE_CREDENTIAL"):
            self.assertFalse(rules.is_interactive({"import_source": source}), source)

    def test_form_paths_are_interactive(self):
        for source in ("INTAKE_FORM", "STAFF_PORTAL", "AGENT_PORTAL"):
            self.assertTrue(rules.is_interactive({"import_source": source}), source)

    def test_missing_import_source_fails_closed(self):
        """An unset source is treated as interactive, so a missing required
        field is caught rather than waved through."""
        self.assertTrue(rules.is_interactive({}))
        self.assertTrue(rules.is_interactive({"import_source": ""}))


if __name__ == "__main__":
    unittest.main()
