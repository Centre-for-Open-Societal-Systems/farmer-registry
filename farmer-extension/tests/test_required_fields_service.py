"""Tests for the required fields on the intake service (required_fields.py and
the finalize in household_intake.py): a section's Next, Submit, and the
ingestion worker. They need the registry platform, so they run inside the
staff API image and are skipped elsewhere."""

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("openg2p_registry_core")

from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_farmer_extension.register_domain.services import (
    household_intake as hi,
)
from openg2p_registry_farmer_extension.register_domain.services import (
    required_fields as rf,
)

FARMER = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"
LAND = "11111111-2222-4333-8444-555555555555"


def _run(coroutine):
    return asyncio.run(coroutine)


def _widget(widget_id, label, required=True, options=None, kind="text"):
    widget = {"widget": kind, "widget-id": widget_id, "widget-label": label, "widget-required": required,
              "widget-data-path": f"{FARMER}.{widget_id}"}
    if options:
        widget["widget-data-options"] = options
    return widget


SCHEMA = {"section-title": "Personal information", "panels": [{"widgets": [
    _widget("first_name", "First name"),
    _widget("gender", "Gender", kind="select"),
    _widget("disability_type", "Disability type", options={"actions": [
        {"action": "show", "condition": {"field": f"{FARMER}.disabled", "operator": "equals", "value": True}}]}),
]}]}
LIST_SCHEMA = {"section-title": "Lands", "panels": [{"widgets": [
    {"widget": "table", "widget-id": "lands_table", "widget-label": "Lands", "widget-required": True,
     "widget-data-path": f"{LAND}.records"}]}]}


class _Platform:
    """The platform's save, which records that it was reached."""

    def __init__(self):
        self.saved = []

    async def save_intake_form_submission_with_session(self, *args, **kwargs):
        self.saved.append(args)
        return "saved"


class _Host(rf.RequiredFieldsMixin, _Platform):
    def __init__(self, schema=SCHEMA, is_list=False, existing=None):
        super().__init__()
        self.section = SimpleNamespace(section_ui_schema=schema, is_list=is_list)
        self.existing = existing or {}

    async def _get_section_or_error(self, section_id, session):
        return self.section

    async def _resolve_intake_form_class(self, register_id, session):
        return object

    async def _get_intake_rows(self, intake_class, submission_id, session):
        return self.existing

    async def _messages(self):
        return {}

    async def _optional_register_ids(self, session):
        return []


@pytest.fixture(autouse=True)
def _no_database(monkeypatch):
    async def nothing(*args, **kwargs):
        return {}

    monkeypatch.setattr(rf, "saved_document_labels", nothing)


def _save(host, payload, register=FARMER, submission="s-1", documents=None):
    return _run(host.save_intake_form_submission_with_session(
        submission, "personal", payload, register, "form", FARMER, "alex", None, documents=documents))


def _refused(host, payload, **kwargs) -> str:
    with pytest.raises(G2PRegistryException) as error:
        _save(host, payload, **kwargs)
    return error.value.message


def test_the_mixin_is_ahead_of_the_platform_service_in_the_registered_intake_service():
    mro = hi.HouseholdCheckedIntakeFormDataService.__mro__
    assert mro.index(rf.RequiredFieldsMixin) < mro.index(hi.G2PFarmerIntakeFormDataService)


def test_next_on_a_section_with_a_required_field_empty_is_refused_with_its_label():
    message = _refused(_Host(), [{"first_name": "", "gender": "MALE"}])
    assert message == "Personal information: First name is required. Fill it in before pressing Next."


def test_next_names_every_missing_field():
    message = _refused(_Host(), [{}])
    assert "First name is required" in message and "Gender is required" in message


def test_a_filled_section_is_saved():
    host = _Host()
    assert _save(host, [{"first_name": "Abebe", "gender": "MALE"}]) == "saved"
    assert len(host.saved) == 1


def test_a_field_hidden_by_a_condition_is_not_required_on_next():
    host = _Host()
    assert _save(host, [{"first_name": "Abebe", "gender": "MALE", "disabled": False}]) == "saved"
    assert "Disability type is required" in _refused(
        _Host(), [{"first_name": "Abebe", "gender": "MALE", "disabled": True}])


def test_a_value_already_saved_in_the_row_counts():
    existing = {"r-1": {"first_name": "Abebe", "gender": "MALE"}}
    host = _Host(existing=existing)
    assert _save(host, [{"internal_record_id": "r-1", "first_name": "Abebe"}]) == "saved"
    assert "First name is required" in _refused(
        _Host(existing=existing), [{"internal_record_id": "r-1", "first_name": ""}])


def test_a_required_list_section_with_no_row_is_refused_on_next():
    message = _refused(_Host(LIST_SCHEMA, is_list=True), [], register=LAND)
    assert message == "Lands: at least one entry is required. Add one before pressing Next."
    assert _save(_Host(LIST_SCHEMA, is_list=True), [{"land_size": 1}], register=LAND) == "saved"
    # A row being deleted is not a row that remains.
    assert "at least one entry" in _refused(_Host(LIST_SCHEMA, is_list=True),
                                            [{"edit_action": "DELETE"}], register=LAND)


def test_the_ingestion_worker_saves_what_the_source_holds():
    host = _Host()
    token = rf.unattended.set(True)
    try:
        assert _save(host, [{"first_name": ""}]) == "saved"
    finally:
        rf.unattended.reset(token)
    assert "First name is required" in _refused(_Host(), [{"first_name": ""}])


def _service(monkeypatch, problems):
    service = object.__new__(hi.HouseholdCheckedIntakeFormDataService)
    submission = SimpleNamespace(submission_id="s-1", register_id="farmer", remarks=None, last_updated_at=None)
    calls = []

    async def get_submission(submission_id, session):
        return submission

    async def get_definition(register_id, session):
        return SimpleNamespace(register_mnemonic="Farmer")

    async def required(sub, session):
        return list(problems)

    async def no_messages():
        return {}

    async def farmer_checks(submission_id, session, submission=None, required=None):
        # The real check joins these with the Fayda ID and household problems and refuses.
        calls.append(("farmer_checks", required))
        if required:
            hi.validation_error("; ".join(required))

    async def platform_finalize(self, submission_id, session, *args, **kwargs):
        calls.append(("finalized", args, kwargs.get("bearer_token")))
        return submission

    async def no_token():
        return None

    monkeypatch.setattr(service, "_get_submission_or_error", get_submission, raising=False)
    monkeypatch.setattr(service, "_get_register_definition", get_definition, raising=False)
    monkeypatch.setattr(service, "required_problems_for", required, raising=False)
    monkeypatch.setattr(service, "_messages", no_messages, raising=False)
    monkeypatch.setattr(hi, "check_farmer_submission", farmer_checks)
    monkeypatch.setattr(hi.G2PFarmerIntakeFormDataService, "finalize_submission_with_session",
                        platform_finalize, raising=False)
    monkeypatch.setattr("openg2p_registry_farmer_extension.odk.worker_token.service_token", no_token)
    return service, submission, calls


class _Session:
    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        pass


MISSING = ["Membership: Cooperative member is required. Open Membership, fill it in and save, then submit again."]


def test_the_worker_leaves_an_incomplete_form_as_a_draft_with_the_reason(monkeypatch):
    service, submission, calls = _service(monkeypatch, MISSING)
    session = _Session()
    result = _run(service.finalize_submission_with_session("s-1", session))
    assert result is submission
    assert submission.remarks.startswith("Not submitted: required information is missing.")
    assert "Cooperative member is required" in submission.remarks
    assert session.added == [submission]
    assert calls == []  # never finalized, never raised: the worker task completes


def test_a_person_submitting_an_incomplete_form_is_refused_listing_the_fields(monkeypatch):
    service, submission, calls = _service(monkeypatch, MISSING)
    with pytest.raises(G2PRegistryException) as error:
        _run(service.finalize_submission_with_session("s-1", _Session(), "alex", bearer_token="t"))
    assert error.value.message == MISSING[0]
    assert submission.remarks is None
    assert ("finalized", ("alex",), "t") not in calls
    assert calls == [("farmer_checks", MISSING)]


def test_the_worker_finalizes_a_complete_form(monkeypatch):
    service, submission, calls = _service(monkeypatch, [])
    assert _run(service.finalize_submission_with_session("s-1", _Session())) is submission
    assert submission.remarks is None
    assert calls[-1][0] == "finalized"


def test_a_person_submitting_a_complete_form_finalizes(monkeypatch):
    service, submission, calls = _service(monkeypatch, [])
    _run(service.finalize_submission_with_session("s-1", _Session(), "alex", bearer_token="t"))
    assert calls[-1] == ("finalized", ("alex",), "t")


def test_a_save_by_the_worker_skips_the_section_check_and_a_person_does_not(monkeypatch):
    service = object.__new__(hi.HouseholdCheckedIntakeFormDataService)
    seen = []

    async def refuse(self, *args, **kwargs):
        seen.append(args[0])

    async def passthrough(session, created_by):
        return created_by

    async def section(section_id, session):
        return SimpleNamespace(section_mnemonic="personal")

    async def platform_save(self, *args, **kwargs):
        return "saved"

    monkeypatch.setattr(rf.RequiredFieldsMixin, "refuse_missing_on_save", refuse)
    monkeypatch.setattr("openg2p_registry_farmer_extension.odk.actor.ingest_actor", passthrough)
    monkeypatch.setattr(service, "_get_section_or_error", section, raising=False)
    monkeypatch.setattr(hi.G2PFarmerIntakeFormDataService, "save_intake_form_submission_with_session",
                        platform_save, raising=False)

    def save(created_by):
        return _run(service.save_intake_form_submission_with_session(
            "s-1", "personal", [{}], FARMER, "form", FARMER, created_by, _Savepoints()))

    assert save("system") == "saved" and seen == []
    assert save("alex") == "saved" and seen == ["s-1"]


REFUSED = "Phone Number: yes is not a phone number. Enter it as 0912345678 or +251912345678"


@pytest.fixture
def ingest():
    """The refusals of one ingest task, as odk/actor.py starts them."""
    token = rf.refusals.set({})
    yield
    rf.refusals.reset(token)


def test_the_worker_lists_a_refused_answer_first_in_the_draft(monkeypatch, ingest):
    service, submission, calls = _service(monkeypatch, MISSING)
    assert rf.hold_back("s-1", REFUSED)
    result = _run(service.finalize_submission_with_session("s-1", _Session()))
    assert result is submission
    assert submission.remarks.startswith("Not submitted: some answers were not accepted. Phone Number: yes")
    assert submission.remarks.index(REFUSED) < submission.remarks.index("Cooperative member is required")
    assert calls == []


def test_outside_an_ingest_task_nothing_is_held_back():
    assert rf.hold_back("s-1", REFUSED) is False
    assert rf.held_back("s-1") == []


def test_the_ingest_task_starts_and_drops_its_refusals():
    from openg2p_registry_farmer_extension.odk import actor

    task = SimpleNamespace(name=actor.INGEST_TASK)
    actor._record_ingest(sender=task, kwargs={"ingest_id": "i-1"})
    assert rf.hold_back("s-9", REFUSED) and rf.held_back("s-9") == [REFUSED]
    actor._forget_ingest(sender=task)
    assert rf.held_back("s-9") == [] and rf.hold_back("s-9", REFUSED) is False


def test_the_worker_leaves_a_form_the_farmer_checks_refuse_as_a_draft(monkeypatch):
    service, submission, calls = _service(monkeypatch, [])

    async def duplicate(submission_id, session, submission=None, required=None):
        hi.validation_error("Fayda ID: 123456789012 is already registered to Abebe (FR-1).")

    monkeypatch.setattr(hi, "check_farmer_submission", duplicate)
    result = _run(service.finalize_submission_with_session("s-1", _Session()))
    assert result is submission
    assert "already registered to Abebe" in submission.remarks
    assert submission.remarks.startswith("Not submitted: some answers were not accepted.")
    assert calls == []


def _refusing_save(monkeypatch, failure=None):
    service = object.__new__(hi.HouseholdCheckedIntakeFormDataService)
    submission = SimpleNamespace(submission_id="s-1")

    async def passthrough(session, created_by):
        return created_by

    async def section(section_id, session):
        return SimpleNamespace(section_mnemonic="personal")

    async def platform_save(self, *args, **kwargs):
        if failure:
            raise failure
        hi.validation_error(REFUSED)

    async def get_submission(submission_id, session):
        return submission

    async def no_messages():
        return {}

    monkeypatch.setattr(rf.RequiredFieldsMixin, "refuse_missing_on_save", lambda *a, **k: asyncio.sleep(0))
    monkeypatch.setattr("openg2p_registry_farmer_extension.odk.actor.ingest_actor", passthrough)
    monkeypatch.setattr(service, "_get_section_or_error", section, raising=False)
    monkeypatch.setattr(service, "_get_submission_or_error", get_submission, raising=False)
    monkeypatch.setattr(service, "_messages", no_messages, raising=False)
    monkeypatch.setattr(hi.G2PFarmerIntakeFormDataService, "save_intake_form_submission_with_session",
                        platform_save, raising=False)

    session = _Savepoints()

    def save(created_by):
        return _run(service.save_intake_form_submission_with_session(
            "s-1", "personal", [{}], FARMER, "form", FARMER, created_by, session))

    return save, submission, session


class _Savepoints:
    """A session whose savepoints record how they ended."""

    def __init__(self):
        self.ended = []

    def begin_nested(self):
        session = self

        class _Nested:
            async def __aenter__(self):
                return self

            async def __aexit__(self, kind, error, trace):
                session.ended.append("rolled back" if error else "released")
                return False

        return _Nested()


def test_a_refused_section_saved_by_the_worker_is_held_back_not_raised(monkeypatch, ingest):
    save, submission, session = _refusing_save(monkeypatch)
    assert save("system") is submission
    assert rf.held_back("s-1") == [REFUSED]
    assert session.ended == ["rolled back"]  # the section is taken back whole


def test_a_refused_section_saved_by_a_person_is_still_refused(monkeypatch, ingest):
    save, _, session = _refusing_save(monkeypatch)
    with pytest.raises(G2PRegistryException) as error:
        save("alex")
    assert REFUSED in error.value.message
    assert rf.held_back("s-1") == []
    assert session.ended == []  # a person's save is unchanged


def test_a_failure_that_is_not_a_refusal_still_fails_the_worker(monkeypatch, ingest):
    lookup = G2PRegistryException(code="G2P-REG-500", message="Master Data is not reachable")
    save, _, session = _refusing_save(monkeypatch, failure=lookup)
    with pytest.raises(G2PRegistryException) as error:
        save("system")
    assert error.value is lookup  # the task retries it, as before
    assert rf.held_back("s-1") == []
    assert session.ended == ["rolled back"]


def test_later_sections_of_the_register_survive_a_refused_one(monkeypatch, ingest):
    """The platform carries a register's earlier answers into its later
    sections: a refused name must not take the location and documents with it,
    and the reason is listed once."""
    service = object.__new__(hi.HouseholdCheckedIntakeFormDataService)
    submission = SimpleNamespace(submission_id="s-1")
    schemas = {
        "personal": {"panels": [{"widgets": [
            {"widget": "text", "widget-id": "first_name_local", "widget-data-path": f"{FARMER}.first_name_local"}]}]},
        "location": {"panels": [{"widgets": [
            {"widget": "geo-hierarchy", "widget-id": "geo", "widget-data-path": {
                "value": f"{FARMER}.geo_lowest_level_value_id", "hierarchy": f"{FARMER}.geo_code_hierarchy_json"}}]}]},
        "documents": {"panels": [{"widgets": [
            {"widget": "select", "widget-id": "identity_document_type", "widget-data-path": f"{FARMER}.identity_document_type"}]}]},
    }
    saved = []

    async def passthrough(session, created_by):
        return created_by

    async def section(section_id, session):
        return SimpleNamespace(section_mnemonic=section_id, section_ui_schema=schemas[section_id])

    async def platform_save(self, submission_id, section_id, payload, *args, **kwargs):
        if any(record.get("first_name_local") == "Tsegay" for record in payload):
            hi.validation_error(REFUSED_NAME)
        saved.append((section_id, sorted(payload[0])))
        return submission

    async def get_submission(submission_id, session):
        return submission

    async def no_messages():
        return {}

    monkeypatch.setattr("openg2p_registry_farmer_extension.odk.actor.ingest_actor", passthrough)
    monkeypatch.setattr(service, "_get_section_or_error", section, raising=False)
    monkeypatch.setattr(service, "_get_submission_or_error", get_submission, raising=False)
    monkeypatch.setattr(service, "_messages", no_messages, raising=False)
    monkeypatch.setattr(hi.G2PFarmerIntakeFormDataService, "save_intake_form_submission_with_session",
                        platform_save, raising=False)
    record = {"internal_record_id": "r-1", "first_name_local": "Tsegay"}
    for section_id, answers in (("personal", {}), ("location", {"geo_lowest_level_value_id": "ET01010101"}),
                                ("documents", {"identity_document_type": "FAYDA"})):
        record = {**record, **answers}  # what the worker merges into each later section
        _run(service.save_intake_form_submission_with_session(
            "s-1", section_id, [dict(record)], FARMER, "form", FARMER, "system", _Savepoints()))
    assert saved == [
        ("location", ["geo_lowest_level_value_id", "internal_record_id"]),
        ("documents", ["geo_lowest_level_value_id", "identity_document_type", "internal_record_id"])]
    assert rf.held_back("s-1") == [REFUSED_NAME]


REFUSED_NAME = "First name (farmer's language): Tigrinya is written in Ethiopic (Ge'ez) script, and \"Tsegay\" is not."


def test_a_reason_is_kept_once(ingest):
    assert rf.hold_back("s-2", REFUSED) and rf.hold_back("s-2", REFUSED)
    assert rf.held_back("s-2") == [REFUSED]
