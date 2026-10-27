"""Tests for the farmer's household at intake finalize
(services/household_intake.py). They need the registry platform, so they run
inside the staff API image and are skipped elsewhere."""

import pytest

pytest.importorskip("openg2p_registry_core")

from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_oan_extension.register_domain.services import (
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
    assert _refused([{}], None, [], {"oan_household_none": "Abwarwa: ..."}) == "Abwarwa: ..."


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
