"""Tests for the derived values and the Ethiopian calendar.

derived.py and ethiopian_calendar.py have no framework imports. They are loaded
as a stand-in package, so these tests run without the registry installed:

    uv run --no-project --with pytest pytest farmer-extension/tests
"""

import importlib
import sys
import types
from datetime import date, timedelta
from pathlib import Path

import pytest

_package = types.ModuleType("oan_register_domain")
_package.__path__ = [str(Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension/register_domain")]
sys.modules["oan_register_domain"] = _package
derived = importlib.import_module("oan_register_domain.derived")
calendar = importlib.import_module("oan_register_domain.ethiopian_calendar")


def test_new_year_anchors():
    # Meskerem 1 is 11 September, or 12 September before a Gregorian leap year.
    assert calendar.gregorian_to_ethiopic(date(2023, 9, 12)) == (2016, 1, 1)
    assert calendar.gregorian_to_ethiopic(date(2024, 9, 11)) == (2017, 1, 1)
    assert calendar.gregorian_to_ethiopic(date(2023, 9, 11)) == (2015, 13, 6)


def test_round_trip_over_a_leap_cycle():
    day = date(2020, 1, 1)
    while day < date(2025, 1, 1):
        assert calendar.ethiopic_to_gregorian(*calendar.gregorian_to_ethiopic(day)) == day
        day += timedelta(days=1)


def test_hectares():
    assert derived.hectares(2, "HECTARE") == 2
    assert derived.hectares(1, "ACRE") == 0.404686
    assert derived.hectares(5000, "SQUARE_METER") == 0.5
    assert derived.hectares("3", None) == 3
    assert derived.hectares(None, "ACRE") is None


def test_land_rollup():
    rollup = derived.land_rollup([("OWNER", 2.5), ("TENANT", 3.5), ("CROP_SHARE", 1.0)])
    assert rollup == {"total_land_area": 7.0, "total_land_owned_area": 2.5, "total_land_rent_area": 3.5,
                      "total_land_crop_sharing_area": 1.0, "land_ownership": "HYBRID"}
    assert derived.land_rollup([("OWNER", 1), ("OWNER", 2)])["land_ownership"] == "OWNER"
    assert derived.land_rollup([("CROP_SHARE", 1)])["land_ownership"] == "HYBRID"
    assert derived.land_rollup([])["land_ownership"] is None
    assert derived.land_rollup([])["total_land_area"] == 0


def test_geo_names():
    hierarchy = {"hierarchy": [
        {"level_mnemonic": "country", "level_value_mnemonic": "Ethiopia"},
        {"level_mnemonic": "region", "level_value_mnemonic": "Tigray"},
        {"level_mnemonic": "zone", "level_value_mnemonic": "North Western"},
        {"level_mnemonic": "woreda", "level_value_mnemonic": "Tahtay Adiyabo"},
        {"level_mnemonic": "kebele", "level_value_mnemonic": "Badme"}]}
    assert derived.geo_names(hierarchy) == {"region_name": "Tigray", "zone_name": "North Western",
                                            "woreda_name": "Tahtay Adiyabo", "kebele_name": "Badme"}
    assert derived.geo_names(None) == dict.fromkeys(("region_name", "zone_name", "woreda_name", "kebele_name"))


def test_ethiopic_twin_follows_the_gregorian_date():
    record = {"birth_date": "1984-08-06", "birth_date_ec": "1900-01-01"}
    derived.ethiopic_twin(record, "birth_date", "birth_date_ec")
    assert record["birth_date_ec"] == "1976-11-30"


def test_ethiopic_twin_is_cleared_with_the_date():
    record = {"birth_date": None, "birth_date_ec": "1976-11-30"}
    derived.ethiopic_twin(record, "birth_date", "birth_date_ec")
    assert record["birth_date_ec"] is None


def test_ethiopic_twin_leaves_partial_updates_alone():
    record = {"gender": "MALE"}
    derived.ethiopic_twin(record, "birth_date", "birth_date_ec")
    assert record == {"gender": "MALE"}


@pytest.mark.parametrize("typed", ["+251 912 345 678", "0912345678", "912345678", "251912345678"])
def test_ethiopian_phone_forms_are_one_number(typed):
    assert derived.normalize_phone(typed) == ("912345678", "+251912345678")


def test_phone_rejects_and_foreign():
    assert derived.normalize_phone("12345") == (None, None)
    assert derived.normalize_phone("") == (None, None)
    assert derived.normalize_phone("+254 712 345678", "KE") == ("+254712345678", "+254712345678")


def test_farmer_search_text_is_ids_and_names_only():
    text = derived.farmer_search_text({
        "functional_record_id": "FR-1", "foundational_id": "121654377346", "rid": None,
        "first_name": "Abebe", "middle_name": "Kebede", "last_name": "Tesfaye", "first_name_local": "አበበ",
        "gender": "MALE", "birth_date": "1984-08-06", "education_level": "PRIMARY", "latitude": 14.4})
    assert text == "FR-1 121654377346 Abebe Kebede Tesfaye አበበ"


def test_local_name_in_a_geez_language_must_be_geez():
    assert derived.local_name_problems({"language_spoken": "AMHARIC", "first_name_local": "አበበ"}) == []
    problem, = derived.local_name_problems({"language_spoken": "TIGRINYA", "first_name_local": "Abebe"})
    assert problem.startswith("First name (farmer's language): Tigrinya is written in Ethiopic (Ge'ez) script")


def test_local_name_in_a_latin_language_is_kept_as_typed():
    assert derived.local_name_problems({"language_spoken": "AFAAN_OROMO", "first_name_local": "Caaltuu"}) == []


def test_local_name_needs_its_language():
    problem, = derived.local_name_problems({"language_spoken": None, "first_name_local": "Caaltuu"})
    assert problem.startswith("Farmer's language: the name is entered in the farmer's language, but no language is chosen")


@pytest.mark.parametrize("code", ["ET", "et", "KE", "+251", "251", "1"])
def test_a_phone_country_is_a_country_code_or_a_dialing_code(code):
    assert derived.valid_country_code(code)


@pytest.mark.parametrize("code", ["ETH", "Ethiopia", "+", "+25100", "E1", "E"])
def test_a_three_letter_or_malformed_country_is_not_one(code):
    assert not derived.valid_country_code(code)


def test_the_ethiopian_dialing_code_reads_an_ethiopian_number():
    assert derived.normalize_phone("0912345678", "+251") == ("912345678", "+251912345678")


def test_email_fills_emails_list():
    record = {"email": " Odk@Example.org "}
    assert derived.sync_email(record) == []
    assert record["email"] == "odk@example.org"  # stored in lower case
    assert record["emails"] == [{"address": "odk@example.org", "is_primary": True}]


def test_emails_list_fills_email_primary_first():
    record = {"emails": [{"address": "a@example.org"}, {"address": "b@example.org", "is_primary": True}]}
    assert derived.sync_email(record) == []
    assert record["email"] == "b@example.org"
    assert derived.email_of([{"address": " "}]) is None
    assert derived.email_of(None) is None


def test_blank_email_clears_emails():
    record = {"email": "  ", "emails": [{"address": "a@example.org", "is_primary": True}]}
    assert derived.sync_email(record) == []
    assert record["email"] is None and record["emails"] is None


def test_record_without_either_is_left_alone():
    record = {"first_name": "Abebe"}
    assert derived.sync_email(record) == []
    assert record == {"first_name": "Abebe"}


@pytest.mark.parametrize("bad", ["abebe", "a@b", "a b@example.org", "@example.org", "a@@example.org", "a@example.org" + "x" * 250])
def test_bad_email_is_refused_with_message(bad):
    assert derived.sync_email({"email": bad}) == ["Email: enter an address like name@example.org"]


def test_an_email_of_254_characters_is_kept_and_255_refused():
    def address(length):
        return "a" * (length - len("@example.org")) + "@example.org"

    assert len(address(254)) == 254 and derived.sync_email({"email": address(254)}) == []
    assert derived.sync_email({"email": address(255)}) == ["Email: enter an address like name@example.org"]


def test_an_ingested_email_is_kept_only_when_valid():
    assert derived.ingested_email(" ODK@Example.org ") == "odk@example.org"
    assert derived.ingested_email("not an email") is None
    assert derived.ingested_email("a@b..co") is None
    assert derived.ingested_email(None) is None
