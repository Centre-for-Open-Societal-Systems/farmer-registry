"""Tests for the Master Data values refused on the server (coded_values.py):
gender, language and marital status against their lists, the location id, and
"Has national ID" answered Yes with no Fayda ID. The module has no framework
imports at load time, so these run without the registry installed:

    uv run --no-project --with pytest pytest farmer-extension/tests/test_coded_values.py
"""

import asyncio
import importlib.util
from pathlib import Path

import pytest

_SERVICES = Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension/register_domain/services"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SERVICES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


widget_rules = _load("widget_rules")
coded_values = _load("coded_values")

SAY = widget_rules._Say({})
LISTS = {
    "GENDER": {"MALE": "Male", "FEMALE": "Female"},
    "LANGUAGE": {"AMHARIC": "Amharic", "AFAAN_OROMO": "Afaan Oromo"},
    "MARITAL_STATUS": {"SINGLE": "Single", "MARRIED": "Married"},
}


@pytest.fixture(autouse=True)
def _clean_cache():
    coded_values._cache.clear()


# --- gender, language, marital status ------------------------------------------


def test_codes_on_their_lists_are_accepted():
    record = {"gender": "FEMALE", "language_spoken": "AMHARIC", "marital_status": "MARRIED"}
    assert coded_values.choice_problems(record, SAY, LISTS) == []


def test_blank_and_absent_values_are_not_judged():
    assert coded_values.choice_problems({"gender": "", "language_spoken": None}, SAY, LISTS) == []


def test_an_unknown_gender_names_the_field_and_the_choices():
    assert coded_values.choice_problems({"gender": "XYZ"}, SAY, LISTS) == ["Gender: choose one of Male, Female."]


def test_an_unknown_language_and_marital_status_are_each_refused():
    problems = coded_values.choice_problems({"language_spoken": "KLINGON", "marital_status": "??"}, SAY, LISTS)
    assert problems == [
        "Farmer's language: choose one of Amharic, Afaan Oromo.",
        "Marital status: choose one of Single, Married.",
    ]


def test_the_label_follows_the_translation():
    say = widget_rules._Say({"gender": "Sex"})
    assert coded_values.choice_problems({"gender": "XYZ"}, say, LISTS) == ["Sex: choose one of Male, Female."]


def test_a_list_that_could_not_be_read_is_not_judged():
    assert coded_values.choice_problems({"gender": "XYZ"}, SAY, {}) == []


class _Client:
    def __init__(self, rows=None, fail=False, geo=None):
        self.rows, self.fail, self.geo, self.calls = rows or [], fail, geo, 0

    async def _post(self, path, payload=None, pagination=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Master Data is down")
        return {"attribute_values": [r for r in self.rows if r["attribute_id"] == payload["attribute_id"]]}

    async def _load_geo_index(self):
        if self.fail:
            raise RuntimeError("Master Data is down")
        return self.geo or {}


def _rows():
    return [{"attribute_id": a, "value_code": c, "value_display": t} for a, d in LISTS.items() for c, t in d.items()]


def test_the_lists_are_read_from_master_data_with_their_display_text(monkeypatch):
    client = _Client(rows=_rows())
    monkeypatch.setattr(coded_values, "_client", lambda: client)
    problems = asyncio.run(coded_values.coded_value_problems([{"gender": "XYZ"}, {"gender": "MALE"}], SAY))
    assert problems == ["Gender: choose one of Male, Female."]
    asyncio.run(coded_values.coded_value_problems([{"gender": "XYZ"}], SAY))
    assert client.calls == 1  # cached


def test_master_data_down_does_not_block_a_save(monkeypatch, caplog):
    monkeypatch.setattr(coded_values, "_client", lambda: _Client(fail=True))
    with caplog.at_level("WARNING", logger="oan-coded-values"):
        problems = asyncio.run(coded_values.coded_value_problems(
            [{"gender": "XYZ", "geo_lowest_level_value_id": "ET99"}], SAY))
    assert problems == []
    assert "Master Data could not be read" in caplog.text


# --- Has national ID without a Fayda ID ---------------------------------------


def test_has_national_id_with_a_fayda_id_is_accepted():
    assert coded_values.fayda_problem({"has_national_id": True, "foundational_id": "123456789012"}, SAY) is None
    assert coded_values.fayda_problem({"has_national_id": False, "foundational_id": ""}, SAY) is None


@pytest.mark.parametrize("record", [
    {"has_national_id": True, "foundational_id": ""},
    {"has_national_id": "true", "foundational_id": None},
    {"has_national_id": True},
])
def test_has_national_id_without_a_fayda_id_is_refused(record):
    assert coded_values.fayda_problem(record, SAY) == (
        "Has national ID: answered Yes, but no Fayda ID is entered. Enter the Fayda ID, or answer No.")


def test_a_partial_update_that_does_not_carry_the_fayda_id_is_not_judged():
    assert coded_values.fayda_problem({"internal_record_id": "f-1", "has_national_id": True}, SAY) is None


# --- location ------------------------------------------------------------------


def test_a_location_master_data_knows_is_accepted():
    assert coded_values.location_problem({"geo_lowest_level_value_id": "ET04010101"}, SAY, {"ET04010101"}) is None
    assert coded_values.location_problem({"geo_lowest_level_value_id": ""}, SAY, {"ET04010101"}) is None


def test_an_unknown_kebele_id_is_refused_with_the_fix():
    assert coded_values.location_problem({"geo_lowest_level_value_id": "ET99999999"}, SAY, {"ET04010101"}) == (
        "Location: the place chosen is not in the Master Data list. Choose the region, zone, woreda and kebele again.")


def test_the_location_is_not_judged_when_master_data_has_no_list():
    assert coded_values.location_problem({"geo_lowest_level_value_id": "ET99999999"}, SAY, None) is None


def test_the_unknown_kebele_is_refused_end_to_end(monkeypatch):
    monkeypatch.setattr(coded_values, "_client", lambda: _Client(geo={"ET04010101": {}}))
    problems = asyncio.run(coded_values.coded_value_problems(
        [{"geo_lowest_level_value_id": "ET04010101"}, {"geo_lowest_level_value_id": "ET99999999"}], SAY))
    assert len(problems) == 1 and problems[0].startswith("Location:")
