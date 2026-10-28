"""MDS ownership and fail-closed seeding regressions."""
import copy
import sys
from pathlib import Path

import pytest

SEED = Path(__file__).resolve().parents[2] / "docker/db-seed"
sys.path.insert(0, str(SEED))
import master_data_samples as source
import load_sample_data as loader


def fixtures():
    person = dict(individual_id="test-person", household_id="test-household",
                  given_name="Given", fathers_name="Father", full_name="Given Father Grandfather",
                  gender="MALE", relationship_to_head="SELF", marital_status="MARRIED",
                  education_level="PRIMARY", disability_status="NO", national_id="123456789012",
                  birth_date="1984-08-06", country="ETH", geo_pcode="ET01010102",
                  address_parts={"house_number": "1"}, phone=None)
    household = dict(household_id="test-household", head_individual_id="test-person",
                     size_total=1, country="ETH", geo_pcode="ET01010102")
    codes = {name: {person[field]} for field, name in source.CODED.items()}
    codes["HEAD_ROLES"] = {"SELF"}
    return [person], [household], {"ET01010102"}, codes


def test_source_names_and_codes_are_preserved_without_fabricated_fields():
    args = fixtures()
    before = copy.deepcopy(args)
    people, households = source.adapt_samples(*args)
    assert args == before
    assert people[0]["last_name"] == "Grandfather"
    assert households[0]["head"] == people[0]
    loader._GEO_BY_ID = {"ET01010102": ("kebele", "Test", None)}
    payload = loader.person_fields(people[0])
    assert payload["foundational_id"] == "123456789012"
    assert payload["education_level"] == "PRIMARY"
    for invented in ("prefix", "occupation", "income_level", "emails", "altitude", "plus_code"):
        assert invented not in payload
    assert payload["phone_numbers"] is None
    assert loader.member_payload(people[0], "household", is_head=True)["relationship_to_the_head"] == "SELF"


@pytest.mark.parametrize("problem", ["empty", "name", "code", "geo", "head", "size", "national_id", "duplicate", "orphan"])
def test_invalid_mds_source_is_rejected_before_intake(problem):
    people, households, geo, codes = fixtures()
    if problem == "empty": people = []
    elif problem == "name": people[0]["full_name"] = "Given Father"
    elif problem == "code": people[0]["gender"] = "not-published"
    elif problem == "geo": geo = set()
    elif problem == "head": households[0]["head_individual_id"] = "missing"
    elif problem == "size": households[0]["size_total"] = 2
    elif problem == "national_id": people[0]["national_id"] = None
    elif problem == "duplicate": people.append(copy.deepcopy(people[0]))
    elif problem == "orphan": people[0]["household_id"] = "missing"
    with pytest.raises(ValueError):
        source.adapt_samples(people, households, geo, codes)


def test_missing_mds_never_falls_back():
    with pytest.raises(ValueError, match="MD_PG"):
        source.load_samples(lambda: None, {})


def test_missing_geography_is_not_replaced_by_first_leaf():
    loader._GEO_BY_ID = {"ET01010102": ("kebele", "Test", None)}
    with pytest.raises(ValueError, match="absent"):
        loader.geo_for_record({"geo_pcode": "not-in-mds"})


@pytest.mark.parametrize("registered,pending,household_intakes,result", [
    ([], 0, 0, False), ([("123456789012",)], 0, 0, True),
    ([], 1, 0, None), ([], 0, 1, None),
    ([("123456789012",), ("123456789012",)], 0, 0, None),
])
def test_source_identity_rerun_guard(monkeypatch, registered, pending, household_intakes, result):
    from unittest.mock import MagicMock
    _, households = source.adapt_samples(*fixtures())
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = registered
    cursor.fetchone.side_effect = [(pending,), (household_intakes,)]
    monkeypatch.setattr(loader, "registry_connect", lambda: conn)
    if result is None:
        with pytest.raises(RuntimeError, match="Partial or existing"):
            loader.already_seeded(households)
    else:
        assert loader.already_seeded(households) is result
    conn.close.assert_called_once()
