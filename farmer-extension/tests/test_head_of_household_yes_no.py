""""Head of household" in the members tables reads Yes or No, and stays a boolean.

The members table prints a cell as it is unless the column is a select, which
it shows by its option label; a boolean column read "true" / "false". The
overlay turns the is_head column of both members tables into a select with the
static options YES (true) and NO (false). These tests apply the overlay's rule
to the seed sections and check the result with the server's widget rules.
"""

import importlib.util
import json
import re
from pathlib import Path

META = Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension/meta_data"
OVERLAY = META / "zz-oan/92_head_of_household_yes_no.sql"
SEED = META / "register-metadata/g2p_register_sections.sql"
SECTIONS = {"farmer_household_household_member_section_02", "household_household_household_member_section_02"}
MEMBER_REGISTER = "52979fdd-220c-48dd-8de0-0a434e786427"

_spec = importlib.util.spec_from_file_location(
    "widget_rules", Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension/register_domain/services/widget_rules.py")
widget_rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(widget_rules)


def overlay():
    return OVERLAY.read_text(encoding="utf-8")


def replacement() -> dict:
    return json.loads(re.search(r"\|\| '(\{.*?\})'::jsonb", overlay(), re.S).group(1))


def seed_sections() -> dict[str, dict]:
    found = {}
    for line in SEED.read_text(encoding="utf-8").splitlines():
        ids = re.findall(r"'([a-z_0-9]+_section_[0-9]+)'", line)
        if ids and ids[0] in SECTIONS:
            found[ids[0]] = json.loads(re.search(r"'(\{\"panels.*?\})'", line).group(1).replace("''", "'"))
    return found


def apply(node):
    """The overlay's rule, in Python."""
    if isinstance(node, list):
        return [apply(item) for item in node]
    if isinstance(node, dict):
        result = {key: apply(value) for key, value in node.items()}
        if node.get("column-key") == "is_head" and node.get("widget") == "boolean":
            result.pop("widget-data-format", None)
            result.update(replacement())
        return result
    return node


def columns(schema):
    if isinstance(schema, dict):
        for column in schema.get("widget-data-columns") or []:
            yield column
        for value in schema.values():
            yield from columns(value)
    elif isinstance(schema, list):
        for value in schema:
            yield from columns(value)


def test_the_seed_has_a_boolean_head_column_in_both_members_tables():
    sections = seed_sections()
    assert set(sections) == SECTIONS
    for schema in sections.values():
        head = [c for c in columns(schema) if c.get("column-key") == "is_head"]
        assert [c["widget"] for c in head] == ["boolean"]


def test_the_head_column_becomes_a_yes_no_select_with_boolean_values():
    assert replacement() == {"widget": "select", "widget-data-source": {"type": "static", "options": [
        {"label": "YES", "value": True}, {"label": "NO", "value": False}]}}
    for schema in seed_sections().values():
        head = next(c for c in columns(apply(schema)) if c.get("column-key") == "is_head")
        assert head["widget"] == "select" and "widget-data-format" not in head
        for kept in ("widget-label", "widget-data-path", "widget-data-default", "widget-required", "widget-data-helptext"):
            assert kept in head, kept
        assert head["widget-data-default"] is False


def test_the_other_columns_are_unchanged():
    for schema in seed_sections().values():
        before = [c for c in columns(schema) if c.get("column-key") != "is_head"]
        after = [c for c in columns(apply(schema)) if c.get("column-key") != "is_head"]
        assert before == after


def test_the_server_still_takes_true_and_false_and_refuses_text():
    rules = widget_rules.collect_rules([(MEMBER_REGISTER, apply(s)) for s in seed_sections().values()])
    field_rules = rules[MEMBER_REGISTER]
    # The other required columns are reported alike for every answer; only the
    # head answer differs.
    yes = widget_rules.check_record({"is_head": True}, field_rules, {})
    assert widget_rules.check_record({"is_head": False}, field_rules, {}) == yes
    refused = widget_rules.check_record({"is_head": "maybe"}, field_rules, {})
    assert [p for p in refused if p not in yes] and all("maybe" not in p for p in yes)


def test_only_the_two_members_tables_and_idempotent():
    text = overlay()
    assert set(re.findall(r"'([a-z_0-9]+_section_02)'", text)) == SECTIONS
    assert "node->>'widget' = 'boolean'" in text  # a second run finds a select and changes nothing
