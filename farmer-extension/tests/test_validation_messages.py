"""Tests for the checks that run on save, validate and submit, and for the
plain messages: the phone service, validate matching submit, and an unknown
household. They need the registry platform, so they run inside the staff API
image and are skipped elsewhere."""

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("openg2p_registry_core")

from openg2p_registry_core.errors import G2PRegistryErrorCodes, G2PRegistryException
from openg2p_registry_core.schemas.intake_form import (
    IntakeSubmissionValidationIssue,
    ValidateIntakeFormSubmissionData,
)
from openg2p_registry_farmer_extension.register_domain.services import (
    household_intake as hi,
)
from openg2p_registry_farmer_extension.register_domain.services.farmer_phone import (
    FarmerPhoneService,
)


def _run(coroutine):
    return asyncio.run(coroutine)


def _refused(coroutine) -> str:
    with pytest.raises(G2PRegistryException) as error:
        _run(coroutine)
    return error.value.message


# --- phone ---------------------------------------------------------------------


def test_a_valid_phone_row_is_accepted_with_either_country_form():
    rows = [{"phone_number": "0912345678", "country_code": "ET"}, {"phone_number": "0922345678", "country_code": "+251"}]
    _run(FarmerPhoneService().validate_domain_attributes(rows))
    assert rows[0]["phone_e164"] == "+251912345678" and rows[1]["phone_e164"] == "+251922345678"


def test_the_three_letter_country_code_is_refused_with_the_fix():
    assert _refused(FarmerPhoneService().validate_domain_attributes(
        [{"phone_number": "0912000300", "country_code": "ETH"}])) == (
        "Country code: ETH is not a country code. Enter the 2-letter country code, for example ET, "
        "or the dialing code, for example +251.")


@pytest.mark.parametrize("rows, message", [
    ([{"phone_number": "09ABCDEFGH"}],
     "Phone number: 09ABCDEFGH is not a phone number. Enter it as 0912345678 or +251912345678."),
    ([{"phone_number": ""}], "Phone number: a row has no number. Enter the number, or remove the row."),
    ([{"phone_number": "0912345678"}, {"phone_number": "0912345678"}],
     "Phone number: the same number is listed twice. Keep one row for it and remove the other."),
])
def test_phone_messages_are_plain_sentences(rows, message):
    assert _refused(FarmerPhoneService().validate_domain_attributes(rows)) == message


# --- an unknown household -------------------------------------------------------

RAW = "link_internal_record_id '00000000-0000-4000-8000-000000000000' does not exist in register 'Household'"


def _service(monkeypatch):
    service = object.__new__(hi.HouseholdCheckedIntakeFormDataService)

    async def no_messages():
        return {}

    monkeypatch.setattr(service, "_messages", no_messages, raising=False)
    return service


def _saving(monkeypatch, message):
    service = _service(monkeypatch)

    async def section(section_id, session):
        return SimpleNamespace(section_mnemonic="personal")

    async def platform_save(self, *args, **kwargs):
        raise G2PRegistryException(code=G2PRegistryErrorCodes.INVALID_REQUEST.value[1], message=message)

    async def passthrough(session, created_by):
        return created_by

    monkeypatch.setattr(service, "_get_section_or_error", section, raising=False)
    monkeypatch.setattr("openg2p_registry_farmer_extension.odk.actor.ingest_actor", passthrough)
    monkeypatch.setattr(hi.RequiredFieldsMixin, "save_intake_form_submission_with_session", platform_save)
    return service.save_intake_form_submission_with_session("s-1", "sec", [{}], "reg", "form", "reg", "alex", None)


def test_a_save_with_an_unknown_household_says_so_in_plain_words(monkeypatch):
    assert _refused(_saving(monkeypatch, RAW)) == "Household not found. Check the household ID."


def test_a_save_error_that_is_not_a_known_message_is_left_as_it_is(monkeypatch):
    with pytest.raises(G2PRegistryException) as error:
        _run(_saving(monkeypatch, "Something else"))
    assert error.value.message == "Something else"
    assert error.value.code == G2PRegistryErrorCodes.INVALID_REQUEST.value[1]


# --- validate says what submit says ---------------------------------------------

MISSING = ["Membership: Cooperative member is required. Open Membership, fill it in and save, then submit again."]


def _validating(monkeypatch, problems, platform_issues=()):
    service = _service(monkeypatch)
    submission = SimpleNamespace(submission_id="s-1", register_id="farmer")

    async def get_submission(submission_id, session):
        return submission

    async def get_definition(register_id, session):
        return SimpleNamespace(register_mnemonic="Farmer")

    async def required(sub, session):
        return list(problems)

    async def farmer_checks(submission_id, session, submission=None, required=None):
        if required:
            hi.validation_error("; ".join(required))

    async def platform_validate(self, submission_id, session):
        return ValidateIntakeFormSubmissionData(
            submission_id=submission_id, is_valid=not platform_issues, issues=list(platform_issues))

    monkeypatch.setattr(service, "_get_submission_or_error", get_submission, raising=False)
    monkeypatch.setattr(service, "_get_register_definition", get_definition, raising=False)
    monkeypatch.setattr(service, "required_problems_for", required, raising=False)
    monkeypatch.setattr(hi, "check_farmer_submission", farmer_checks)
    monkeypatch.setattr(hi.DirectApprovalClosed, "validate_submission_for_approval_with_session",
                        platform_validate, raising=False)
    return service


def test_validate_reports_a_complete_draft_as_valid(monkeypatch):
    service = _validating(monkeypatch, [])
    result = _run(service.validate_submission_for_approval_with_session("s-1", None))
    assert result.is_valid and result.issues == []


def test_validate_reports_the_draft_that_submit_refuses(monkeypatch):
    service = _validating(monkeypatch, MISSING)
    result = _run(service.validate_submission_for_approval_with_session("s-1", None))
    assert not result.is_valid
    assert [issue.message for issue in result.issues] == MISSING
    # Submit refuses the same text.
    message = _refused(service.refuse_unsubmittable(
        SimpleNamespace(submission_id="s-1"), SimpleNamespace(register_mnemonic="Farmer"), MISSING, None))
    assert message == MISSING[0]


def test_validate_says_an_unknown_household_in_plain_words(monkeypatch):
    issue = IntakeSubmissionValidationIssue(code="INVALID_PARENT_LINK", message=RAW)
    service = _validating(monkeypatch, [], platform_issues=[issue])
    result = _run(service.validate_submission_for_approval_with_session("s-1", None))
    assert [i.message for i in result.issues] == ["Household not found. Check the household ID."]
    assert not result.is_valid


# --- the Farmer's own checks refuse the bad values ------------------------------


def _farmer_service(monkeypatch, lists, geo=None):
    from openg2p_registry_farmer_extension.register_domain import services as extension
    from openg2p_registry_farmer_extension.register_domain.services import coded_values

    class Client:
        async def _post(self, path, payload=None, pagination=None):
            return {"attribute_values": [
                {"attribute_id": a, "value_code": c, "value_display": t}
                for a, d in lists.items() for c, t in d.items() if a == payload["attribute_id"]]}

        async def _load_geo_index(self):
            return geo or {}

    async def load():
        return {}, {}, {}

    coded_values._cache.clear()
    monkeypatch.setattr(coded_values, "_client", lambda: Client())
    monkeypatch.setattr(extension, "_load", load)
    return extension.G2PRegisterDomainServiceFarmer()


GENDERS = {"GENDER": {"MALE": "Male", "FEMALE": "Female"}}


def test_a_farmer_with_listed_codes_and_a_fayda_id_is_accepted(monkeypatch):
    from openg2p_registry_farmer_extension.register_domain.services import form_integrity

    async def nobody_else_holds_it(*args, **kwargs):
        return None

    monkeypatch.setattr(form_integrity, "check_fayda_id_unique", nobody_else_holds_it)
    service = _farmer_service(monkeypatch, GENDERS, geo={"ET04010101": {}})
    _run(service.validate_domain_attributes([{
        "first_name": "Abebe", "last_name": "Kebede", "gender": "MALE", "has_national_id": True,
        "foundational_id": "123456789012", "geo_lowest_level_value_id": "ET04010101"}]))


def test_a_farmer_with_an_unknown_gender_is_refused(monkeypatch):
    service = _farmer_service(monkeypatch, GENDERS)
    assert _refused(service.validate_domain_attributes(
        [{"first_name": "Abebe", "last_name": "Kebede", "gender": "XYZ"}])) == "Gender: choose one of Male, Female."


def test_a_farmer_with_has_national_id_and_no_fayda_id_is_refused(monkeypatch):
    service = _farmer_service(monkeypatch, GENDERS)
    message = _refused(service.validate_domain_attributes(
        [{"first_name": "Abebe", "last_name": "Kebede", "has_national_id": True, "foundational_id": ""}]))
    assert message.startswith("Has national ID: answered Yes, but no Fayda ID is entered.")


def test_a_farmer_with_an_unknown_kebele_is_refused(monkeypatch):
    service = _farmer_service(monkeypatch, GENDERS, geo={"ET04010101": {}})
    message = _refused(service.validate_domain_attributes(
        [{"first_name": "Abebe", "last_name": "Kebede", "geo_lowest_level_value_id": "ET99999999"}]))
    assert message.startswith("Location: the place chosen is not in the Master Data list.")
