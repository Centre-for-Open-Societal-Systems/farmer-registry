"""Tests for the required fields read from the section metadata
(services/required_fields.py). The module has no framework imports, so it is
loaded from the services directory without the package __init__ and these
tests run without the registry installed:

    uv run --no-project --with pytest pytest farmer-extension/tests
"""

import importlib
import sys
import types
from pathlib import Path

_DIR = Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension/register_domain/services"
_package = types.ModuleType("oan_services_pure")
_package.__path__ = [str(_DIR)]
sys.modules.setdefault("oan_services_pure", _package)
rf = importlib.import_module("oan_services_pure.required_fields")

FARMER = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"
MESSAGES = {"gender": "Gender", "marital_status": "Marital Status", "farmer_personal_details": "Personal Details",
            "farmer_identity": "Identity", "fayda_fin": "Fayda ID (FIN / FAN)", "household_members": "Household Members"}


def widget(widget_id, kind="text", required=False, options=None, label=None, **extra):
    found = {"widget": kind, "widget-id": widget_id, "widget-label": label or widget_id,
             "widget-required": required, "widget-data-path": f"{FARMER}.{widget_id}", **extra}
    if options:
        found["widget-data-options"] = options
    return found


def column(key, required=False, options=None):
    found = {"widget": "text", "column-key": key, "widget-label": key, "widget-required": required,
             "widget-data-path": key}
    if options:
        found["widget-data-options"] = options
    return found


def equals(field, value, prefix=True):
    return {"field": f"{FARMER}.{field}" if prefix else field, "operator": "equals", "value": value}


def section(title, *widgets):
    return {"section-title": title, "panels": [{"widgets": list(widgets)}]}


def table_section(title, columns, required=False):
    return {"section-title": title, "panels": [{"widgets": [
        {"widget": "table", "widget-id": "rows", "widget-required": required, "widget-data-columns": columns}]}]}


PERSONAL = section(
    "farmer_personal_details",
    widget("gender", "select", required=True, label="gender"),
    widget("birth_date", "date", required=True, label="birth_date"),
    widget("marital_status", "select", required=True, label="marital_status"),
    widget("estimated_age", "number"),
)


def problems(schema, record, *, is_list=False, messages=MESSAGES, files=None, records=None):
    rows = records if records is not None else ([record] if record is not None else [])
    return rf.section_problems(schema, is_list, rows, {FARMER: rows[0] if rows else {}}, messages, files)


def test_an_empty_required_section_names_every_missing_field():
    assert problems(PERSONAL, {}) == ["Personal Details: fill in Gender, Birth date, Marital Status"]


def test_an_untranslated_name_reads_without_underscores():
    result = problems(PERSONAL, {"gender": "MALE"}, messages={})
    assert result == ["Farmer personal details: fill in Birth date, Marital status"]
    assert "_" not in result[0]


def test_a_complete_section_has_nothing_missing():
    assert problems(PERSONAL, {"gender": "MALE", "birth_date": "1990-01-01", "marital_status": "SINGLE"}) == []


def test_blank_values_are_missing_but_false_and_zero_are_answers():
    schema = section("s", widget("flag", "boolean", required=True), widget("count", "number", required=True))
    assert problems(schema, {"flag": False, "count": 0}) == []
    assert problems(schema, {"flag": None, "count": "  "}) == ["S: fill in Flag, Count"]


def test_a_hidden_field_is_not_required():
    schema = section("s", widget("has_id", "boolean"),
                     widget("fin", required=True, options={"actions": [{"action": "show", "condition": equals("has_id", True)}]}))
    assert problems(schema, {"has_id": False}) == []
    assert problems(schema, {"has_id": True}) == ["S: fill in Fin"]


def test_a_require_rule_makes_an_optional_field_required():
    schema = section("s", widget("disabled", "boolean"),
                     widget("kind", "select", options={"actions": [{"action": "require", "condition": equals("disabled", True)}]}))
    assert problems(schema, {"disabled": False}) == []
    assert problems(schema, {"disabled": True}) == ["S: fill in Kind"]


def test_the_last_show_or_hide_rule_wins():
    schema = section("s", widget("a", "boolean"), widget("b", "boolean"),
                     widget("x", required=True, options={"actions": [
                         {"action": "hide", "condition": equals("a", True)},
                         {"action": "show", "condition": equals("b", True)}]}))
    assert problems(schema, {"a": True, "b": False}) == []
    assert problems(schema, {"a": True, "b": True}) == ["S: fill in X"]


def test_a_condition_may_look_at_another_section_of_the_form():
    schema = section("s", widget("x", required=True, options={"actions": [
        {"action": "show", "condition": equals("has_id", True)}]}))
    shown = rf.section_problems(schema, False, [{}], {FARMER: {"has_id": True}}, {})
    hidden = rf.section_problems(schema, False, [{}], {FARMER: {"has_id": False}}, {})
    assert shown == ["S: fill in X"] and hidden == []


def test_readonly_lookups_and_display_widgets_are_left_alone():
    schema = section("s", widget("lookup", "register-lookup", required=True), widget("shown", "display", required=True),
                     widget("locked", required=True, **{"widget-readonly": True}))
    assert problems(schema, {}) == []


def test_a_required_table_needs_a_row():
    schema = table_section("household_members", [column("first_name", required=True)], required=True)
    assert problems(schema, None, is_list=True, records=[]) == ["Household Members: add at least one row"]


def test_an_optional_table_may_be_empty():
    schema = table_section("lands", [column("land_size", required=True)])
    assert problems(schema, None, is_list=True, records=[]) == []


def test_each_row_needs_its_required_columns():
    schema = table_section("household_members", [column("first_name", required=True), column("gender", required=True)])
    rows = [{"first_name": "Abebe", "gender": "MALE"}, {"first_name": "Almaz", "gender": ""}]
    assert problems(schema, None, is_list=True, records=rows) == ["Household Members, row 2: fill in Gender"]


def test_a_hidden_column_is_not_required():
    schema = table_section("crops", [
        column("is_diseased"),
        column("disease_type", required=True,
               options={"actions": [{"action": "show", "condition": equals("is_diseased", True, prefix=False)}]})])
    assert problems(schema, None, is_list=True, records=[{"is_diseased": False}]) == []
    assert problems(schema, None, is_list=True, records=[{"is_diseased": True}]) == ["Crops, row 1: fill in Disease type"]


def test_a_required_document_is_a_file_to_add():
    schema = section("farmer_documents", widget("identity_document_1", "file", required=True,
                                                  options={"title": "identity_documents"}))
    messages = {"identity_documents": "Identity proof", "farmer_documents": "Documents"}
    assert problems(schema, {}, messages=messages) == ["Documents: add Identity proof"]
    assert problems(schema, {}, messages=messages, files={"identity_document_1"}) == []


def test_the_geo_widget_is_read_from_its_value_path():
    schema = section("farmer_location", widget("farmer_geo_hierarchy", "geo-hierarchy", required=True,
                                               **{"widget-data-path": {"value": f"{FARMER}.geo_lowest_level_value_id"}}))
    assert problems(schema, {}) == ["Farmer location: fill in Farmer geo hierarchy"]
    assert problems(schema, {"geo_lowest_level_value_id": "ET010101"}) == []
