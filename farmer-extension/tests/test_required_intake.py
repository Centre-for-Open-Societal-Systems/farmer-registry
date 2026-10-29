"""Tests for the required fields at save and submit (services/required_intake.py).

They need the registry platform for its validation error, so they run inside
the staff API image and are skipped elsewhere. The platform's intake service is
replaced by a small stand-in that holds what a submission stores, so the mixin
is exercised end to end: a section save, then a finalize, the way the web UI,
the ODK worker and a partner push call it.
"""

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("openg2p_registry_core")

from openg2p_registry_core.errors import G2PRegistryException  # noqa: E402

_DIR = Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension/register_domain/services"
_package = types.ModuleType("oan_services_pure")
_package.__path__ = [str(_DIR)]
sys.modules.setdefault("oan_services_pure", _package)
ri = importlib.import_module("oan_services_pure.required_intake")

FARMER = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"
HOUSEHOLD = "9055ab43-c85d-4833-bd00-ca657bb72644"
MESSAGES = {"gender": "Gender", "farmer_personal_details": "Personal Details", "farmer_lands": "Lands",
            "household_information": "Household Information", "farmer_documents": "Documents"}


def _widget(widget_id, register=FARMER, required=False, kind="text", options=None):
    found = {"widget": kind, "widget-id": widget_id, "widget-label": widget_id, "widget-required": required,
             "widget-data-path": f"{register}.{widget_id}"}
    if options:
        found["widget-data-options"] = options
    return found


def _section(section_id, register, is_list, ui, mnemonic=None):
    return types.SimpleNamespace(section_id=section_id, section_register_id=register, is_list=is_list,
                                 section_ui_schema=ui, section_mnemonic=mnemonic or section_id)


PERSONAL = _section("farmer_personal_details", FARMER, False, {
    "section-title": "farmer_personal_details",
    "panels": [{"widgets": [_widget("gender", required=True), _widget("marital_status", required=True)]}]})
IDENTITY = _section("farmer_identity", FARMER, False, {
    "section-title": "farmer_identity",
    "panels": [{"widgets": [
        _widget("has_national_id", kind="boolean"),
        _widget("foundational_id", options={"actions": [
            {"action": "show", "condition": {"field": f"{FARMER}.has_national_id", "operator": "equals", "value": True}},
            {"action": "require", "condition": {"field": f"{FARMER}.has_national_id", "operator": "equals", "value": True}}]}),
    ]}]})
LANDS = _section("farmer_lands", "land", True, {
    "section-title": "farmer_lands",
    "panels": [{"widgets": [{"widget": "table", "widget-id": "lands_table", "widget-required": True,
                            "widget-data-columns": [{"widget": "number", "column-key": "land_size", "widget-label": "land_size",
                                                     "widget-required": True, "widget-data-path": "land_size"}]}]}]})
HOUSEHOLD_INFO = _section("household_information", HOUSEHOLD, False, {
    "section-title": "household_information",
    "panels": [{"widgets": [_widget("size_of_group", register=HOUSEHOLD, required=True, kind="number")]}]})


class Platform:
    """What the real intake service would do after the checks: it saved."""

    async def save_intake_form_submission_with_session(self, submission_id, section_id, section_payload,
                                                       section_register_id, form_id, register_id, created_by,
                                                       session, documents=None):
        self.stored.setdefault(section_register_id, {})
        for record in section_payload:
            self.stored[section_register_id].setdefault(record["internal_record_id"], {}).update(
                {k: v for k, v in record.items() if k != "edit_action"})
        return "saved"

    async def finalize_submission_with_session(self, submission_id, session, *args, **kwargs):
        return "finalized"


class Service(ri.RequiredFieldsMixin, Platform):
    """The mixin over a stand-in that stores records in a dict."""

    picked_parent_skips = {"Farmer": frozenset({"Household"})}

    def __init__(self, sections):
        self.sections = {s.section_id: s for s in sections}
        self.stored = {}
        self.files = {}

    async def _required_messages(self):
        return MESSAGES

    async def _get_section_or_error(self, section_id, session):
        return self.sections[section_id]

    async def _stored_records(self, submission_id, section_register_id, session):
        return dict(self.stored.get(section_register_id, {})) if submission_id else {}

    async def _stored_file_labels(self, submission_id, section_id, session):
        return set(self.files.get(section_id, ()))

    async def _get_submission_or_error(self, submission_id, session):
        return types.SimpleNamespace(submission_id=submission_id, form_id="form", register_id=FARMER)

    async def _get_form_sections(self, form_id, session):
        return list(self.sections.values())

    async def _section_records(self, submission_id, section, session):
        rows = list(self.stored.get(section.section_register_id, {}).values())
        return rows if section.is_list else rows[:1]

    async def _skipped_registers(self, subject_register_id, subject, own_ids, session):
        link = subject.get("link_internal_record_id")
        return {HOUSEHOLD} if link and link not in own_ids else set()

    @staticmethod
    def _records_for_validation(records):
        return [r for r in records or [] if (r or {}).get("edit_action") != "DELETE"]

    def save(self, section, payload, submission_id="sub-1", documents=None):
        return asyncio.run(self.save_intake_form_submission_with_session(
            submission_id, section.section_id, payload, section.section_register_id, "form", FARMER, "user", None,
            documents=documents))

    def finalize(self):
        return asyncio.run(self.finalize_submission_with_session("sub-1", None))


def _refused(call, *args, **kwargs) -> str:
    with pytest.raises(G2PRegistryException) as error:
        call(*args, **kwargs)
    return error.value.message


def test_saving_an_empty_required_section_is_refused():
    service = Service([PERSONAL])
    message = _refused(service.save, PERSONAL, [{"internal_record_id": "f1"}])
    assert message == "Personal Details: fill in Gender, Marital status"
    assert service.stored == {}


def test_saving_a_section_with_a_required_field_left_out_is_refused():
    service = Service([PERSONAL])
    assert _refused(service.save, PERSONAL, [{"internal_record_id": "f1", "gender": "MALE"}]) == (
        "Personal Details: fill in Marital status")


def test_saving_a_complete_section_passes():
    service = Service([PERSONAL])
    assert service.save(PERSONAL, [{"internal_record_id": "f1", "gender": "MALE", "marital_status": "SINGLE"}]) == "saved"


def test_a_field_saved_earlier_counts_when_the_ui_leaves_it_out():
    service = Service([PERSONAL])
    service.stored[FARMER] = {"f1": {"internal_record_id": "f1", "gender": "MALE", "marital_status": "SINGLE"}}
    assert service.save(PERSONAL, [{"internal_record_id": "f1", "gender": "FEMALE"}]) == "saved"


def test_clearing_a_required_field_is_refused():
    service = Service([PERSONAL])
    service.stored[FARMER] = {"f1": {"internal_record_id": "f1", "gender": "MALE", "marital_status": "SINGLE"}}
    assert _refused(service.save, PERSONAL, [{"internal_record_id": "f1", "gender": None}]) == (
        "Personal Details: fill in Gender")


def test_a_hidden_field_is_not_required_on_save():
    service = Service([IDENTITY])
    assert service.save(IDENTITY, [{"internal_record_id": "f1", "has_national_id": False}]) == "saved"
    assert _refused(service.save, IDENTITY, [{"internal_record_id": "f1", "has_national_id": True}]) == (
        "Farmer identity: fill in Foundational id")


def test_saving_a_required_table_with_no_rows_is_refused():
    service = Service([LANDS])
    assert _refused(service.save, LANDS, []) == "Lands: add at least one row"
    assert _refused(service.save, LANDS, [{"internal_record_id": "l1", "edit_action": "DELETE"}]) == (
        "Lands: add at least one row")


def test_a_table_row_without_its_required_column_is_refused():
    service = Service([LANDS])
    assert _refused(service.save, LANDS, [{"internal_record_id": "l1"}]) == "Lands, row 1: fill in Land size"
    assert service.save(LANDS, [{"internal_record_id": "l1", "land_size": 2}]) == "saved"


def test_finalizing_an_incomplete_submission_is_refused():
    service = Service([PERSONAL, LANDS])
    service.stored[FARMER] = {"f1": {"internal_record_id": "f1", "gender": "MALE"}}
    message = _refused(service.finalize)
    assert message == "Personal Details: fill in Marital status; Lands: add at least one row"


def test_finalizing_a_complete_submission_passes():
    service = Service([PERSONAL, LANDS])
    service.stored[FARMER] = {"f1": {"internal_record_id": "f1", "gender": "MALE", "marital_status": "SINGLE"}}
    service.stored["land"] = {"l1": {"internal_record_id": "l1", "land_size": 1.5}}
    assert service.finalize() == "finalized"


def test_a_section_never_opened_is_refused_at_submit():
    service = Service([PERSONAL])
    assert _refused(service.finalize) == "Personal Details: fill in Gender, Marital status"


def test_the_household_sections_are_left_out_when_a_household_is_picked():
    service = Service([PERSONAL, HOUSEHOLD_INFO])
    service.stored[FARMER] = {"f1": {"internal_record_id": "f1", "gender": "MALE", "marital_status": "SINGLE",
                                     "link_internal_record_id": "registered-household"}}
    assert service.finalize() == "finalized"
    service.stored[FARMER]["f1"]["link_internal_record_id"] = None
    assert _refused(service.finalize) == "Household Information: fill in Size of group"


def test_the_household_entered_on_the_form_is_not_a_pick():
    service = Service([PERSONAL, HOUSEHOLD_INFO])
    service.stored[FARMER] = {"f1": {"internal_record_id": "f1", "gender": "MALE", "marital_status": "SINGLE",
                                     "link_internal_record_id": "hh-new"}}
    service.stored[HOUSEHOLD] = {"hh-new": {"internal_record_id": "hh-new"}}
    assert _refused(service.finalize) == "Household Information: fill in Size of group"


def test_an_incomplete_odk_intake_is_refused_with_a_readable_reason():
    # The ODK worker saves each section from the submission, then finalizes.
    # An answer missing from the submission stops the save with a sentence the
    # ingestion row records; nothing else is raised.
    service = Service([PERSONAL, LANDS])
    submission = [{"internal_record_id": "f1", "gender": "MALE", "oan_documents": {}}]
    message = _refused(service.save, PERSONAL, submission, submission_id=None)
    assert message == "Personal Details: fill in Marital status"
    assert "_" not in message and "REQ-VAL" not in message


def test_an_incomplete_partner_intake_is_refused_at_submit():
    service = Service([PERSONAL, LANDS])
    service.stored[FARMER] = {"f1": {"internal_record_id": "f1", "gender": "MALE", "marital_status": "SINGLE"}}
    assert _refused(service.finalize) == "Lands: add at least one row"


def test_a_document_attached_by_the_worker_counts_as_saved():
    documents = _section("farmer_documents", FARMER, False, {
        "section-title": "farmer_documents",
        "panels": [{"widgets": [_widget("identity_document_1", kind="file", required=True)]}]})
    service = Service([documents])
    assert _refused(service.save, documents, [{"internal_record_id": "f1"}]) == "Documents: add Identity document 1"
    attached = [{"internal_record_id": "f1", "oan_documents": {"farmer_documents": {"identity_document_1": "doc-1"}}}]
    assert service.save(documents, attached) == "saved"
