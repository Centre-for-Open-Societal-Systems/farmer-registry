"""Tests for the required fields over a whole form and on a section's Next
(form_integrity.required_problems). The pure part has no framework imports, so
these run without the registry installed:

    uv run --no-project --with pytest pytest farmer-extension/tests/test_required_fields.py
"""

import importlib
import sys
import types
from pathlib import Path

_DIR = Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension/register_domain/services"
_package = types.ModuleType("oan_services_pure")
_package.__path__ = [str(_DIR)]
sys.modules.setdefault("oan_services_pure", _package)
fi = importlib.import_module("oan_services_pure.form_integrity")

FARMER = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"
MEMBERSHIP = "495f251c-83a5-4025-a307-1925712c9d0b"
HOUSEHOLD = "9055ab43-c85d-4833-bd00-ca657bb72644"
LAND = "11111111-2222-4333-8444-555555555555"


def _w(register, widget_id, kind="text", required=False, options=None, label=None, path=None):
    widget = {"widget": kind, "widget-id": widget_id, "widget-label": label or widget_id,
              "widget-required": required, "widget-data-path": path or f"{register}.{widget_id}"}
    if options:
        widget["widget-data-options"] = options
    return widget


def _section(section_id, title, register, widgets, is_list=False):
    return {"section_id": section_id, "title": title, "register_id": register, "is_list": is_list,
            "schema": {"panels": [{"widgets": widgets}]}}


def _when(register, field, value, action="show"):
    return {"actions": [{"action": action, "condition": {"field": f"{register}.{field}", "operator": "equals",
                                                          "value": value}}]}


PERSONAL = _section("personal", "Personal information", FARMER, [
    _w(FARMER, "first_name", required=True, label="First name"),
    _w(FARMER, "gender", "select", required=True, label="Gender"),
])
MEMBERSHIP_SECTION = _section("membership", "Membership", MEMBERSHIP, [
    _w(MEMBERSHIP, "is_primary_cooperative_member", "select", required=True, label="Cooperative member"),
    _w(MEMBERSHIP, "primary_cooperative_name", required=True, label="Cooperative name",
       options=_when(MEMBERSHIP, "is_primary_cooperative_member", True)),
])
HOUSEHOLD_SECTION = _section("household", "Household information", HOUSEHOLD, [
    _w(HOUSEHOLD, "size_of_group", "number", required=True, label="Household size"),
])
LANDS = _section("lands", "Lands", LAND, [
    {**_w(LAND, "lands_table", "table", required=True, label="Lands"), "widget-data-path": f"{LAND}.records"},
    {"widget": "number", "column-key": "land_size", "widget-required": True},
], is_list=True)
OPTIONAL_CROPS = _section("crops", "Crops", LAND, [
    {**_w(LAND, "crops_table", "table", label="Crops"), "widget-data-path": f"{LAND}.records"},
], is_list=True)
DOCUMENTS = _section("docs", "Documents", FARMER, [
    _w(FARMER, "identity_document_1", "file", required=True, label="Identity document",
       path=f"{FARMER}.documents.identity_document_1"),
])
FORM = [PERSONAL, MEMBERSHIP_SECTION, HOUSEHOLD_SECTION, LANDS, OPTIONAL_CROPS, DOCUMENTS]

COMPLETE_ROWS = {
    FARMER: [{"first_name": "Abebe", "gender": "MALE"}],
    MEMBERSHIP: [{"is_primary_cooperative_member": False}],
    HOUSEHOLD: [{"size_of_group": 3}],
    LAND: [{"land_size": 1.5}],
}
DOCS = {"docs": {"identity_document_1"}}


def _problems(rows, documents=DOCS, **options):
    return fi.required_problems(FORM, rows, documents, **options)


def test_a_complete_form_has_nothing_missing():
    assert _problems(COMPLETE_ROWS) == []


def test_a_register_with_no_record_reports_its_required_fields():
    # A farmer with no membership row used to reach approval.
    rows = {k: v for k, v in COMPLETE_ROWS.items() if k != MEMBERSHIP}
    assert _problems(rows) == [
        "Membership: Cooperative member is required. Open Membership, fill it in and save, then submit again."]


def test_submit_names_each_missing_field_by_its_label():
    rows = {**COMPLETE_ROWS, FARMER: [{"first_name": " ", "gender": None}]}
    assert _problems(rows) == [
        "Personal information: First name is required. Open Personal information, fill it in and save, "
        "then submit again.",
        "Personal information: Gender is required. Open Personal information, fill it in and save, then submit again.",
    ]


def test_save_refuses_a_section_with_a_required_field_empty_naming_it():
    problems = fi.required_problems([PERSONAL], {FARMER: [{"first_name": "", "gender": "MALE"}]}, {}, saving=True)
    assert problems == ["Personal information: First name is required. Fill it in before pressing Next."]


def test_save_passes_a_section_whose_required_fields_are_filled():
    assert fi.required_problems([PERSONAL], {FARMER: [{"first_name": "Abebe", "gender": "MALE"}]}, {},
                                saving=True) == []


def test_a_field_hidden_by_a_condition_is_not_required():
    rows = {**COMPLETE_ROWS, MEMBERSHIP: [{"is_primary_cooperative_member": False, "primary_cooperative_name": ""}]}
    assert _problems(rows) == []


def test_a_shown_field_is_required_and_a_filled_one_passes():
    member = {"is_primary_cooperative_member": True}
    assert _problems({**COMPLETE_ROWS, MEMBERSHIP: [member]}) == [
        "Membership: Cooperative name is required. Open Membership, fill it in and save, then submit again."]
    assert _problems({**COMPLETE_ROWS, MEMBERSHIP: [{**member, "primary_cooperative_name": "Yirga"}]}) == []


def test_a_false_or_zero_answer_counts_as_an_answer():
    rows = {**COMPLETE_ROWS, MEMBERSHIP: [{"is_primary_cooperative_member": False}],
            HOUSEHOLD: [{"size_of_group": 0}]}
    assert _problems(rows) == []


def test_a_required_list_section_with_no_row_is_refused():
    rows = {k: v for k, v in COMPLETE_ROWS.items() if k != LAND}
    assert _problems(rows) == [
        "Lands: at least one entry is required. Open Lands, add one and save, then submit again."]
    assert fi.required_problems([LANDS], {LAND: []}, {}, saving=True) == [
        "Lands: at least one entry is required. Add one before pressing Next."]


def test_a_required_list_section_with_a_row_passes_and_an_optional_one_may_be_empty():
    assert fi.required_problems([LANDS, OPTIONAL_CROPS], {LAND: [{"land_size": 2}]}, {}) == []
    assert fi.required_problems([OPTIONAL_CROPS], {}, {}) == []


def test_a_required_document_is_missing_until_saved():
    assert _problems(COMPLETE_ROWS, documents={}) == [
        "Documents: Identity document is required. Open Documents, add the file and save, then submit again."]
    assert fi.required_problems([DOCUMENTS], {FARMER: [{}]}, {"docs": {"identity_document_1"}}, saving=True) == []
    assert fi.required_problems([DOCUMENTS], {FARMER: [{}]}, {"docs": set()}, saving=True) == [
        "Documents: Identity document is required. Add the file before pressing Next."]


def test_an_optional_register_is_checked_only_once_the_submission_holds_a_record():
    rows = {k: v for k, v in COMPLETE_ROWS.items() if k != HOUSEHOLD}
    assert _problems(rows, optional_registers=[HOUSEHOLD]) == []  # a household is picked instead
    assert len(_problems(rows)) == 1  # a household's own form requires it
    blank = {**rows, HOUSEHOLD: [{"size_of_group": None}]}
    assert _problems(blank, optional_registers=[HOUSEHOLD]) == [
        "Household information: Household size is required. Open Household information, fill it in and save, "
        "then submit again."]


def test_the_other_registers_a_condition_reads_are_named():
    schema = {"panels": [{"widgets": [
        _w(FARMER, "x", options=_when(MEMBERSHIP, "y", True)),
        _w(FARMER, "z", options={"action": "disable", "condition": {"field": "local", "operator": "empty"}}),
    ]}]}
    assert fi.condition_registers(schema) == {MEMBERSHIP}


def test_a_condition_on_another_register_uses_that_registers_record():
    section = _section("farmer", "Farmer", FARMER, [
        _w(FARMER, "reason", required=True, label="Reason", options=_when(MEMBERSHIP, "is_member", True))])
    assert fi.required_problems([section], {FARMER: [{}], MEMBERSHIP: [{"is_member": False}]}, {}) == []
    assert fi.required_problems([section], {FARMER: [{}], MEMBERSHIP: [{"is_member": True}]}, {}, saving=True) == [
        "Farmer: Reason is required. Fill it in before pressing Next."]


def test_messages_can_be_translated():
    messages = {"save_missing": "{section} - {label}: da zama dole"}
    assert fi.required_problems([PERSONAL], {FARMER: [{"first_name": "", "gender": "M"}]}, {}, messages,
                                saving=True) == ["Personal information - First name: da zama dole"]
