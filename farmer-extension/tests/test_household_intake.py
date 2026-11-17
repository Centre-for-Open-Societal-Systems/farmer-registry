"""Tests for the farmer's household at intake finalize
(services/household_intake.py). They need the registry platform, so they run
inside the staff API image and are skipped elsewhere."""

import pytest

pytest.importorskip("openg2p_registry_core")

from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_farmer_extension.register_domain.services import (
    household_intake as hi,
)

HOUSEHOLD = {"internal_record_id": "hh-new", "size_of_group": 2}
HEAD = {"is_head": True, "gender": "MALE"}
WIFE = {"is_head": False, "gender": "FEMALE", "relationship_to_the_head": "SPOUSE"}


def _refused(*args, **kwargs) -> str:
    with pytest.raises(G2PRegistryException) as error:
        hi.check_farmer_household(*args, **kwargs)
    return error.value.message


def test_a_picked_household_alone_is_accepted():
    hi.check_farmer_household([{"link_internal_record_id": "hh-1"}], None, [])


def test_a_new_household_with_its_members_is_accepted():
    hi.check_farmer_household([{"link_internal_record_id": None}], dict(HOUSEHOLD), [dict(HEAD), dict(WIFE)])


def test_the_farmer_linked_to_the_new_household_is_not_a_pick():
    hi.check_farmer_household([{"link_internal_record_id": "hh-new"}], dict(HOUSEHOLD), [dict(HEAD), dict(WIFE)])


def test_picking_a_household_and_entering_a_new_one_is_refused():
    message = _refused([{"link_internal_record_id": "hh-1"}], dict(HOUSEHOLD), [dict(HEAD), dict(WIFE)])
    assert message.startswith("Household: an existing household is picked")
    assert "clear the household lookup" in message


def test_no_household_at_all_is_refused_with_both_ways_to_fix_it():
    message = _refused([{"link_internal_record_id": ""}], None, [])
    assert "Pick the farmer's household" in message and "enter a new household" in message


def test_a_new_household_is_checked_by_the_farmer_extension_roster_rules():
    assert "Household members must be entered" in _refused([{}], dict(HOUSEHOLD), [])
    assert "marked as the head" in _refused([{}], dict(HOUSEHOLD), [dict(WIFE), dict(WIFE)])


def test_members_without_the_household_information_are_refused():
    assert "Household information must be entered" in _refused([{}], None, [dict(HEAD)])


def test_a_translation_replaces_the_message():
    assert _refused([{}], None, [], {"household_none": "Abwarwa: ..."}) == "Abwarwa: ..."


ALMAZ = {"first_name": "Almaz", "middle_name": "Desta", "last_name": "Bekele", "is_household_head": True}


def test_a_new_household_takes_its_head_from_the_farmer_on_the_form():
    household = dict(HOUSEHOLD)
    assert hi.new_household_head_problems([dict(ALMAZ)], household) == []
    assert household["household_head"] == "Almaz Desta Bekele"


def test_a_new_household_naming_someone_else_as_head_is_refused():
    household = {**HOUSEHOLD, "household_head": "Tesfaye Alemu"}
    [problem] = hi.new_household_head_problems([dict(ALMAZ)], household)
    assert "names Tesfaye Alemu" in problem and "Enter Almaz Desta Bekele" in problem


def test_a_farmer_who_is_not_the_head_leaves_the_new_household_as_entered():
    household = dict(HOUSEHOLD)
    assert hi.new_household_head_problems([{**ALMAZ, "is_household_head": False}], household) == []
    assert "household_head" not in household


def test_heading_a_registered_household_needs_a_change_request_on_it_first():
    household = {"functional_record_id": "HH-0001", "household_head": "Tesfaye Alemu"}
    [problem] = hi.household_head_problems("Almaz Desta Bekele", household, [])
    assert "HH-0001, whose registered head is Tesfaye Alemu" in problem
    assert "change request on that household" in problem and "answer No" in problem


def test_heading_a_registered_household_that_already_names_the_farmer_is_accepted():
    household = {"functional_record_id": "HH-0001", "household_head": " almaz  desta bekele"}
    assert hi.household_head_problems("Almaz Desta Bekele", household, []) == []


def test_another_farmer_still_heading_the_household_is_named_with_the_fix():
    household = {"functional_record_id": "HH-0001", "household_head": "Almaz Desta Bekele"}
    [problem] = hi.household_head_problems("Almaz Desta Bekele", household, ["Tesfaye Alemu"])
    assert "Tesfaye Alemu is already the head of HH-0001" in problem
    assert "change request on Tesfaye Alemu's record" in problem


# Core keeps a chosen parent link when a save sends it blank, so a household
# removed in the lookup stayed on the draft. A blank link sent by the section
# that picks it now clears the stored one before core's save.
LOOKUP_SECTION = {"section-id": "farmer_household_lookup", "panels": [{"panel-widgets": [
    {"widget": "register-lookup", "widget-id": "household",
     "widget-data-path": "farmer-reg.link_internal_record_id"},
    {"widget": "radio", "widget-id": "is_household_head", "widget-data-path": "farmer-reg.is_household_head"}]}]}
LAND_SECTION = {"section-id": "farmer_lands", "panels": [{"panel-widgets": [
    {"widget": "text", "widget-id": "land_id", "widget-data-path": "land-reg.land_id"}]}]}


def test_the_household_lookup_section_picks_the_farmer_link():
    assert hi.picks_link(LOOKUP_SECTION, "farmer-reg")
    assert not hi.picks_link(LOOKUP_SECTION, "land-reg")
    assert not hi.picks_link(LAND_SECTION, "land-reg")
    assert not hi.picks_link(None, "farmer-reg")


def test_a_blank_link_in_the_payload_removes_it_and_an_omitted_one_does_not():
    assert hi.removes_link([{"link_internal_record_id": None, "is_household_head": True}])
    assert hi.removes_link([{"link_internal_record_id": ""}])
    assert not hi.removes_link([{"link_internal_record_id": "hh-1"}])
    assert not hi.removes_link([{"is_household_head": False}])
    assert not hi.removes_link([])


class _Row:
    def __init__(self, link):
        self.link_internal_record_id = link


class _Session:
    flushed = False

    async def flush(self):
        self.flushed = True


def test_clear_link_drops_the_link_on_the_submission_rows(monkeypatch):
    import asyncio

    from openg2p_registry_farmer_extension.register_domain.services import (
        form_integrity,
    )

    rows = [_Row("hh-old"), _Row(None)]
    seen = {}

    async def fake_rows(register_id, submission_id, session):
        seen["args"] = (register_id, submission_id)
        return rows

    monkeypatch.setattr(form_integrity, "intake_rows", fake_rows)
    session = _Session()
    asyncio.run(hi.clear_link("farmer-reg", "sub-1", session))
    assert seen["args"] == ("farmer-reg", "sub-1")
    assert [r.link_internal_record_id for r in rows] == [None, None]
    assert session.flushed
