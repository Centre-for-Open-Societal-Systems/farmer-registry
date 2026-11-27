"""Tests for the whole-form checks at submit (form_integrity.py).

The pure part has no framework imports, so it is loaded from the services
directory without the package's __init__ and these tests run without the
registry installed:

    uv run --no-project --with pytest pytest farmer-extension/tests
"""

import importlib
import sys
import types
from pathlib import Path

_DIR = Path(__file__).parents[1] / "src/openg2p_registry_oan_farmer_extension/register_domain/services"
_package = types.ModuleType("oan_services_pure")
_package.__path__ = [str(_DIR)]
sys.modules.setdefault("oan_services_pure", _package)
fi = importlib.import_module("oan_services_pure.form_integrity")

FARMER = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"
HOUSEHOLD = "9055ab43-c85d-4833-bd00-ca657bb72644"


def _w(widget_id, kind="text", required=False, options=None, path=None, label=None):
    widget = {"widget": kind, "widget-id": widget_id, "widget-label": label or widget_id,
              "widget-required": required, "widget-data-path": path or f"{FARMER}.{widget_id}"}
    if options:
        widget["widget-data-options"] = options
    return widget


def _equals(field, value):
    return {"field": f"{FARMER}.{field}", "operator": "equals", "value": value}


SECTIONS = [
    {"section_id": "identity", "title": "Identity", "schema": {"panels": [{"widgets": [
        _w("has_national_id", "boolean", required=True),
        _w("foundational_id", options={"actions": [{"action": "show", "condition": _equals("has_national_id", True)},
                                                   {"action": "require", "condition": _equals("has_national_id", True)}]}),
    ]}]}},
    {"section_id": "personal", "title": "Personal details", "schema": {"panels": [{"widgets": [
        _w("gender", "select", required=True,
           options={"action": "disable", "condition": _equals("last_authentication_status", "SUCCESS")}),
        _w("disability_type", "select", options={"actions": [
            {"action": "show", "condition": _equals("disabled", True)},
            {"action": "require", "condition": _equals("disabled", True)}]}),
    ]}]}},
    {"section_id": "location", "title": "Location", "schema": {"panels": [{"widgets": [
        _w("farmer_geo_hierarchy", "geo-hierarchy", required=True,
           path={"value": f"{FARMER}.geo_lowest_level_value_id", "hierarchy": f"{FARMER}.geo_code_hierarchy_json"}),
        _w("household_lookup", "register-lookup", required=True, path=f"{FARMER}.link_internal_record_id"),
    ]}]}},
    {"section_id": "household", "title": "Household information", "schema": {"panels": [{"widgets": [
        _w("size_of_group", "number", required=True, path=f"{HOUSEHOLD}.size_of_group"),
    ]}]}},
    {"section_id": "docs", "title": "Documents", "schema": {"panels": [{"widgets": [
        _w("identity_document_1", "file", required=True, path=f"{FARMER}.documents.identity_document_1"),
    ]}]}},
]

COMPLETE = {"has_national_id": True, "foundational_id": "412345678901", "gender": "MALE",
            "geo_lowest_level_value_id": "ET010101001"}


def _missing(record, documents=None):
    if documents is None:
        documents = {"docs": {"identity_document_1"}}
    return fi.missing_required(SECTIONS, FARMER, {FARMER: record}, documents)


def test_a_complete_form_has_nothing_missing():
    assert _missing(dict(COMPLETE)) == []


def test_an_unopened_section_reports_each_required_field_by_section():
    problems = _missing({"has_national_id": False})
    assert "Personal details: Gender is required. Open Personal details, fill it in and save, then submit again." in problems
    assert any(p.startswith("Location: Farmer geo hierarchy is required") for p in problems)


def test_a_hidden_field_is_never_required():
    # foundational_id is shown and required only when has_national_id is Yes.
    assert not any("Foundational id" in p for p in _missing({**COMPLETE, "has_national_id": False, "foundational_id": None}))


def test_a_require_rule_makes_a_shown_field_required():
    problems = _missing({**COMPLETE, "foundational_id": ""})
    assert problems == ["Identity: Foundational id is required. Open Identity, fill it in and save, then submit again."]


def test_a_conditional_requirement_follows_its_condition():
    assert any("Disability type" in p for p in _missing({**COMPLETE, "disabled": True}))
    assert _missing({**COMPLETE, "disabled": False}) == []


def test_a_false_answer_counts_as_an_answer():
    assert not any("Has national id" in p for p in _missing({**COMPLETE, "has_national_id": False}))


def test_a_missing_required_document_names_its_section():
    problems = _missing(dict(COMPLETE), documents={})
    assert problems == ["Documents: Identity document 1 is required. Open Documents, add the file and save, then submit again."]


def test_a_document_category_is_named_by_its_title():
    sections = [{"section_id": "docs", "title": "Documents", "schema": {"panels": [{"widgets": [
        _w("identity_document_1", "file", required=True, path=f"{FARMER}.documents.identity_document_1",
           options={"title": "identity_documents", "slots": []}),
    ]}]}}]
    problems = fi.missing_required(sections, FARMER, {FARMER: {}}, {}, {"identity_documents": "Identity proof"})
    assert problems == ["Documents: Identity proof is required. Open Documents, add the file and save, then submit again."]


def test_lookups_and_other_registers_are_left_to_their_own_checks():
    problems = _missing(dict(COMPLETE))
    assert not any("household_lookup" in p or "size_of_group" in p for p in problems)


def test_labels_and_titles_are_translated():
    messages = {"gender": "Gender", "Personal details": "Personal details (translated)"}
    problems = fi.missing_required(SECTIONS, FARMER, {FARMER: {**COMPLETE, "gender": None}},
                                   {"docs": {"identity_document_1"}}, messages)
    assert problems == [("Personal details (translated): Gender is required. Open Personal details (translated), "
                         "fill it in and save, then submit again.")]


def test_conditions_match_the_ui_engine():
    values = {FARMER: {"flag": True, "text": "TRUE", "n": 3, "blank": "", "items": ["A"]}}
    match = fi.condition_matches
    assert match(_equals("flag", True), values)
    assert not match(_equals("text", True), values)  # a boolean value needs a boolean field
    assert match(_equals("flag", "yes"), values)  # a boolean field takes a boolean-like value
    assert match({"field": f"{FARMER}.blank", "operator": "empty"}, values)
    assert not match({"field": f"{FARMER}.blank", "operator": "notEmpty"}, values)
    assert match({"field": f"{FARMER}.n", "operator": "greaterThan", "value": 2}, values)
    assert match({"field": f"{FARMER}.items", "operator": "contains", "value": "A"}, values)
    assert match({"field": f"{FARMER}.items", "operator": "notContains", "value": "B"}, values)
    assert not match({"field": f"{FARMER}.n", "operator": "unknown"}, values)


def test_the_last_show_or_hide_rule_wins():
    widget = _w("x", options={"actions": [{"action": "hide", "condition": _equals("a", True)},
                                         {"action": "show", "condition": _equals("b", True)}]})
    assert fi.widget_state(widget, {FARMER: {"a": True, "b": True}}) == (True, False)
    assert fi.widget_state(widget, {FARMER: {"a": True, "b": False}}) == (False, False)


def test_fayda_ids_compare_without_spaces():
    assert fi.fayda_id(" 0012 3456 7890 1234 ") == "0012345678901234"
    assert fi.fayda_id("   ") is None
    assert fi.fayda_id(None) is None


def test_the_holder_is_named_by_record_name_or_names():
    assert fi.holder_name({"record_name": "Abebe Kebede"}) == "Abebe Kebede"
    assert fi.holder_name({"first_name": "Abebe", "middle_name": None, "last_name": "Kebede"}) == "Abebe Kebede"
    assert fi.holder_name({}) == "an unnamed farmer"


def test_a_second_form_with_the_fayda_id_of_one_pending_approval_is_refused_naming_it(monkeypatch):
    """Two ODK submissions of the same farmer: the second one's Submit finds the first, already
    submitted and pending approval, and says which it is (the worker keeps it as a draft with
    this reason)."""
    import asyncio
    from types import SimpleNamespace

    async def holder(fin, *, internal_record_id, submission_id, session):
        assert submission_id == "s-2"
        row = SimpleNamespace(first_name="Abebe", middle_name="Kebede", last_name="Tesfaye", submission_id="s-1")
        return "pending", (row, "2026NOV17-00001ABCDE")

    monkeypatch.setattr(fi, "fayda_id_holder", holder)
    said = asyncio.run(fi.check_fayda_id_unique(
        {"foundational_id": "123456789012"}, "Fayda ID", None, {}, submission_id="s-2"))
    assert "123456789012" in said and "2026NOV17-00001ABCDE" in said


# A field the officer can no longer see is cleared on save (hidden_fields).
IDENTITY = SECTIONS[0]["schema"]


def test_a_field_hidden_by_its_rule_is_cleared_and_a_shown_one_is_kept():
    hidden = fi.hidden_fields(IDENTITY, FARMER, {FARMER: {"has_national_id": False, "foundational_id": "123"}})
    assert hidden == {"foundational_id"}
    assert fi.hidden_fields(IDENTITY, FARMER, {FARMER: {"has_national_id": True, "foundational_id": "123"}}) == set()


def test_a_field_one_visible_widget_writes_is_never_cleared():
    schema = {"panels": [{"widgets": [
        _w("foundational_id", options={"action": "show", "condition": _equals("has_national_id", True)}),
        _w("fin_copy", path=f"{FARMER}.foundational_id"),
    ]}]}
    assert fi.hidden_fields(schema, FARMER, {FARMER: {"has_national_id": False}}) == set()


def test_a_rule_reading_another_register_never_clears():
    schema = {"panels": [{"widgets": [
        _w("household_note", options={"action": "show", "condition": {
            "field": f"{HOUSEHOLD}.size_of_group", "operator": "greaterThan", "value": 1}}),
    ]}]}
    assert fi.hidden_fields(schema, FARMER, {FARMER: {}, HOUSEHOLD: {"size_of_group": 0}}) == set()


def test_another_register_s_fields_and_tables_are_left_alone():
    schema = {"panels": [{"widgets": [
        _w("size_of_group", path=f"{HOUSEHOLD}.size_of_group",
           options={"action": "show", "condition": _equals("has_national_id", True)}),
        _w("lands", "table", options={"action": "show", "condition": _equals("has_national_id", True)}),
    ]}]}
    assert fi.hidden_fields(schema, FARMER, {FARMER: {"has_national_id": False}}) == set()
