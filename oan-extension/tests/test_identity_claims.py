"""Tests for what a Fayda verification puts on the form (identity_claims.py).

identity_claims.py has no framework imports and is loaded as a stand-in
package, so these run without the registry installed:

    uv run --no-project --with pytest pytest oan-extension/tests
"""

import importlib
import sys
import types
from pathlib import Path

_package = types.ModuleType("oan_register_domain")
_package.__path__ = [str(Path(__file__).parents[1] / "src/openg2p_registry_oan_extension/register_domain")]
sys.modules.setdefault("oan_register_domain", _package)
claims = importlib.import_module("oan_register_domain.identity_claims")

MOCK_PERSON = {
    "sub": "psut-1",
    "individual_id": "123456789012",
    "name#en": "Abebe Kebede Tesfaye",
    "name#am": "አበበ ከበደ ተስፋዬ",
    "gender#en": "Male",
    "birthdate": "1987/05/12",
}


def test_default_mapping_splits_the_three_names_and_codes_the_rest():
    assert claims.map_claims(MOCK_PERSON) == {
        "first_name": "Abebe",
        "middle_name": "Kebede",
        "last_name": "Tesfaye",
        "first_name_local": "አበበ",
        "middle_name_local": "ከበደ",
        "last_name_local": "ተስፋዬ",
        "gender": "MALE",
        "birth_date": "1987-05-12",
    }


def test_fayda_amharic_name_is_the_farmers_name_when_their_language_is_amharic_or_unset():
    values = claims.map_claims(MOCK_PERSON)
    for language in (None, "", "AMHARIC"):
        local = claims.local_name_values(values, language)
        assert local["first_name_local"] == "አበበ"
        assert local["language_spoken"] == "AMHARIC" and local["local_name_from_fayda"] is True


def test_fayda_amharic_name_is_left_out_for_another_language():
    local = claims.local_name_values(claims.map_claims(MOCK_PERSON), "AFAAN_OROMO")
    assert not {"first_name_local", "language_spoken", "local_name_from_fayda"} & set(local)
    assert local["first_name"] == "Abebe"


def test_no_amharic_claim_sets_no_language():
    local = claims.local_name_values({"first_name": "Abebe"}, None)
    assert local == {"first_name": "Abebe"}


def test_a_missing_claim_or_name_part_is_left_for_the_staff():
    values = claims.map_claims({"name": "Almaz Bekele", "gender": "unknown-value"})
    assert values == {"first_name": "Almaz", "middle_name": "Bekele"}


def test_provider_mapping_replaces_the_default():
    mapping = {"first_name": "given_name", "birth_date": {"claim": "dob", "format": "date"}}
    assert claims.map_claims({"given_name": "Sara", "dob": "2001-1-9", "name": "x y z"}, mapping) == {
        "first_name": "Sara",
        "birth_date": "2001-01-09",
    }


def test_language_list_claims_take_the_first_value():
    mapping = {"first_name": {"claim": "name", "part": 0}}
    assert claims.map_claims({"name": [{"language": "eng", "value": "Hana Girma"}]}, mapping) == {"first_name": "Hana"}


def test_same_value_compares_dates_by_day_and_text_without_case():
    assert claims.same_value("1987-05-12", "1987-05-12")
    assert claims.same_value("1987-05-12T00:00:00", "1987-05-12")
    assert claims.same_value(" abebe ", "Abebe")
    assert claims.same_value(None, "Abebe")  # empty contradicts nothing
    assert not claims.same_value("Abebech", "Abebe")
    assert not claims.same_value("1987-05-13", "1987-05-12")


def test_failures_are_explained_with_what_to_do():
    reason = "Token subject (999) does not match registrant record (123)."
    assert "not the FIN on this form" in claims.explain_failure(reason)
    assert claims.explain_failure("anything else").startswith("Fayda could not verify")
    assert claims.explain_failure(None).startswith("Fayda could not verify")
