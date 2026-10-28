"""Tests for the server-side widget rules.

widget_rules.py has no framework imports, so it is loaded by path and these
tests run without the registry installed:

    uv run --no-project --with pytest pytest oan-extension/tests
"""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).parents[1] / "src/oan_farmer_registry_extension/register_domain/services/widget_rules.py"
_spec = importlib.util.spec_from_file_location("widget_rules", _PATH)
widget_rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(widget_rules)

FARMER = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"
LAND = "493153d5-07ef-4743-8efd-07f4099772b9"
ETHIOPIC = "^[\\u1200-\\u137F\\u2D80-\\u2DDF\\uAB00-\\uAB2F ]+$"

PERSONAL = {"panels": [{"panels": [{"widgets": [
    {"widget": "text", "widget-id": "first_name_amh", "widget-label": "first_name_amh", "widget-data-path": f"{FARMER}.first_name_amh",
     "widget-data-validation": {"pattern": ETHIOPIC, "maxLength": 10, "patternMessage": "ethiopic_script_only"}},
    {"widget": "number", "widget-id": "estimated_age", "widget-label": "estimated_age", "widget-data-path": f"{FARMER}.estimated_age",
     "widget-data-format": {"numericType": "integer"}, "widget-data-validation": {"min": 0, "max": 122}},
    {"widget": "boolean", "widget-id": "has_national_id", "widget-label": "has_national_id",
     "widget-data-path": f"{FARMER}.has_national_id"},
    {"widget": "date", "widget-id": "birth_date", "widget-label": "birth_date", "widget-data-path": f"{FARMER}.birth_date"},
    {"widget": "select", "widget-id": "disabled", "widget-label": "disabled", "widget-data-path": f"{FARMER}.disabled",
     "widget-data-source": {"type": "static", "options": [{"label": "YES", "value": True}, {"label": "NO", "value": False}]}},
    {"widget": "select", "widget-id": "gender", "widget-data-path": f"{FARMER}.gender",
     "widget-data-source": {"type": "api", "params": {"attribute_id": "GENDER"}}},
    {"widget": "text", "widget-id": "middle_name", "widget-data-path": f"{FARMER}.middle_name"},
]}]}]}

LANDS = {"panels": [{"panels": [{"widgets": [
    {"widget": "table", "widget-id": "lands_table", "widget-data-path": f"{LAND}.records", "widget-data-columns": [
        {"widget": "number", "column-key": "land_size", "widget-data-path": "land_size",
         "widget-data-validation": {"min": 0.01, "minMessage": "land_size_positive"}},
        {"widget": "text", "column-key": "land_id", "widget-data-path": "land_id",
         "widget-data-validation": {"maxLength": 5}},
    ]},
]}]}]}

RULES = widget_rules.collect_rules([(FARMER, PERSONAL), (LAND, LANDS)])
MESSAGES = {"ethiopic_script_only": "Use Ethiopic (Ge'ez) script", "first_name_amh": "First Name (Amharic)",
            "estimated_age": "Estimated Age", "has_national_id": "Has National ID", "birth_date": "Birth Date",
            "disabled": "Has Disability"}


def test_collects_widget_and_table_column_rules():
    assert set(RULES) == {FARMER, LAND}
    assert set(RULES[FARMER]) == {"first_name_amh", "estimated_age", "has_national_id", "birth_date", "disabled"}
    assert RULES[LAND]["land_size"] == {"min": 0.01, "minMessage": "land_size_positive", "type": "number"}
    assert RULES[LAND]["land_id"] == {"maxLength": 5}


def test_widget_without_rules_is_not_listed():
    assert "middle_name" not in RULES[FARMER]


def test_valid_values_pass():
    record = {"first_name_amh": "አበበ", "estimated_age": 40}
    assert widget_rules.check_record(record, RULES[FARMER], MESSAGES) == []


def test_pattern_uses_the_translated_message():
    problems = widget_rules.check_record({"first_name_amh": "Abebe"}, RULES[FARMER], MESSAGES)
    assert problems == ["First Name (Amharic): Use Ethiopic (Ge'ez) script."]


def test_pattern_message_key_is_used_when_untranslated():
    problems = widget_rules.check_record({"first_name_amh": "Abebe"}, RULES[FARMER], {})
    assert problems == ["first_name_amh: ethiopic_script_only."]


def test_length_and_range():
    problems = widget_rules.check_record({"first_name_amh": "አበበአበበአበበአበ", "estimated_age": 130}, RULES[FARMER], MESSAGES)
    assert problems == ["First Name (Amharic): too long. Enter at most 10 characters.",
                        "Estimated Age: 130 is too large. Enter 122 or less."]


def test_numbers_sent_as_text_are_checked():
    assert widget_rules.check_record({"land_size": "0"}, RULES[LAND]) == ["land_size: 0 is too small. Enter 0.01 or more."]


def test_empty_values_are_left_to_the_required_rules():
    record = {"first_name_amh": "", "estimated_age": None}
    assert widget_rules.check_record(record, RULES[FARMER]) == []


def test_booleans_are_not_numbers():
    assert widget_rules.check_record({"estimated_age": True}, RULES[FARMER], MESSAGES) == [
        'Estimated Age: "True" is not a whole number. Enter digits only, for example 12.']


def test_conflicting_sections_keep_the_first_rule():
    other = {"panels": [{"widgets": [{"widget": "number", "widget-data-path": f"{FARMER}.estimated_age",
                                      "widget-data-validation": {"max": 100}}]}]}
    rules = widget_rules.collect_rules([(FARMER, PERSONAL), (FARMER, other)])
    assert rules[FARMER]["estimated_age"]["max"] == 122


def test_a_pattern_python_cannot_compile_is_skipped():
    rules = {"code": {"pattern": "(?<name"}}
    assert widget_rules.check_record({"code": "x"}, rules) == []


def test_a_yes_no_question_takes_only_yes_or_no():
    assert widget_rules.check_record({"has_national_id": True}, RULES[FARMER], MESSAGES) == []
    assert widget_rules.check_record({"has_national_id": "maybe"}, RULES[FARMER], MESSAGES) == [
        "Has National ID: answer Yes or No."]


def test_a_whole_number_is_required_where_the_format_says_integer():
    assert widget_rules.check_record({"estimated_age": "ten"}, RULES[FARMER], MESSAGES) == [
        'Estimated Age: "ten" is not a whole number. Enter digits only, for example 12.']
    assert widget_rules.check_record({"estimated_age": 40.5}, RULES[FARMER], MESSAGES) == [
        'Estimated Age: "40.5" is not a whole number. Enter digits only, for example 12.']


def test_a_date_must_be_a_real_day():
    assert widget_rules.check_record({"birth_date": "1980-05-01"}, RULES[FARMER], MESSAGES) == []
    assert widget_rules.check_record({"birth_date": "1980-02-30"}, RULES[FARMER], MESSAGES) == [
        'Birth Date: "1980-02-30" is not a date. Pick the date from the calendar (DD/MM/YYYY).']


def test_a_static_select_takes_only_its_options():
    assert widget_rules.check_record({"disabled": False}, RULES[FARMER], MESSAGES) == []
    assert widget_rules.check_record({"disabled": "sometimes"}, RULES[FARMER], MESSAGES) == [
        'Has Disability: "sometimes" is not one of the choices. Pick one from the list.']


def test_an_api_select_is_not_checked_here():
    assert "gender" not in RULES[FARMER]


def test_messages_can_be_reworded_per_language():
    words = {**MESSAGES, "rule_boolean": "{label}: choose Yes or No"}
    assert widget_rules.check_record({"has_national_id": 3}, RULES[FARMER], words) == ["Has National ID: choose Yes or No"]


def test_numbers_sent_as_text_become_numbers():
    record = {"estimated_age": "40", "land_size": " 2.5 ", "first_name_amh": "12"}
    widget_rules.normalize_record(record, {**RULES[FARMER], **RULES[LAND]})
    assert record == {"estimated_age": 40, "land_size": 2.5, "first_name_amh": "12"}


def test_text_that_is_not_a_number_is_left_for_the_check():
    record = {"estimated_age": "ten", "land_size": "4.5"}
    widget_rules.normalize_record(record, RULES[FARMER])
    assert record == {"estimated_age": "ten", "land_size": "4.5"}


LIVESTOCK = "4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb"
HERD = {"widgets": [{"widget": "table", "widget-data-path": f"{LIVESTOCK}.records", "widget-data-columns": [
    {"widget": "parent-lookup", "column-key": "link_internal_record_id", "widget-required": True},
    {"widget": "select", "column-key": "livestock_type", "widget-label": "livestock_type", "widget-required": True,
     "widget-data-source": {"type": "api"}},
    {"widget": "number", "column-key": "head_count", "widget-label": "head_count", "widget-required": True,
     "widget-data-options": {"actions": [{"action": "require", "condition": {"field": "x", "value": 1}}]}},
]}]}
HERD_RULES = widget_rules.collect_rules([(LIVESTOCK, HERD)])[LIVESTOCK]
WORDS = {"livestock_type": "Livestock Type"}


def test_a_required_column_is_required_in_a_new_row():
    assert widget_rules.check_record({"livestock_type": ""}, HERD_RULES, WORDS) == [
        "Livestock Type: this is required. Fill it in on every row before saving."]
    assert widget_rules.check_record({"livestock_type": "CATTLE"}, HERD_RULES, WORDS) == []


def test_an_existing_row_that_does_not_send_a_required_column_is_not_rejected():
    assert widget_rules.check_record({"internal_record_id": "r1"}, HERD_RULES, WORDS) == []
    assert widget_rules.check_record({"internal_record_id": "r1", "livestock_type": " "}, HERD_RULES, WORDS) == [
        "Livestock Type: this is required. Fill it in on every row before saving."]


def test_the_parent_link_and_conditional_columns_are_left_to_their_own_checks():
    assert "link_internal_record_id" not in HERD_RULES
    assert "required" not in HERD_RULES.get("head_count", {})


def test_a_section_field_is_never_required_here():
    assert not any("required" in rule for rule in RULES[FARMER].values())


def test_a_bound_with_its_own_message_uses_it():
    words = {"land_size": "Land Size", "land_size_positive": "Enter a size greater than 0"}
    assert widget_rules.check_record({"land_size": 0}, RULES[LAND], words) == ["Land Size: Enter a size greater than 0."]


def test_a_field_without_a_label_is_named_by_its_translation():
    rules = widget_rules.collect_rules([(FARMER, {"widgets": [
        {"widget": "number", "widget-data-path": f"{FARMER}.latitude", "widget-data-validation": {"max": 90}}]})])
    assert widget_rules.check_record({"latitude": 100}, rules[FARMER], {"latitude": "Latitude"}) == [
        "Latitude: 100 is too large. Enter 90 or less."]


def test_a_whole_number_wins_over_any_number_when_screens_differ():
    loose = {"widgets": [{"widget": "number", "widget-data-path": f"{FARMER}.estimated_age"}]}
    rules = widget_rules.collect_rules([(FARMER, loose), (FARMER, PERSONAL)])
    assert rules[FARMER]["estimated_age"]["type"] == "integer"


def test_an_untranslated_label_falls_back_to_the_fields_translation():
    rules = widget_rules.collect_rules([(FARMER, {"widgets": [
        {"widget": "number", "widget-label": "gps_lat", "widget-data-path": f"{FARMER}.latitude",
         "widget-data-validation": {"max": 90}}]})])
    assert widget_rules.check_record({"latitude": 100}, rules[FARMER], {"latitude": "Latitude"}) == [
        "Latitude: 100 is too large. Enter 90 or less."]


def test_multi_select_static_schema_checks_every_answer_and_required_empty_list():
    schema={"widgets":[{"widget":"table","widget-data-path":f"{FARMER}.records",
        "widget-data-columns":[{"widget":"multi-select","column-key":"finance_access_types",
        "widget-data-path":"finance_access_types","widget-label":"Financial services","widget-required":True,
        "widget-data-source":{"type":"static","options":[{"value":"LOAN"},{"value":"INSURANCE"}]}}]}]}
    rules=widget_rules.collect_rules([(FARMER,schema)])[FARMER]
    assert widget_rules.check_record({"finance_access_types":["LOAN","INSURANCE"]},rules)==[]
    problems=widget_rules.check_record({"finance_access_types":["LOAN","UNKNOWN"]},rules)
    assert len(problems)==1 and 'UNKNOWN' in problems[0] and 'Financial services' in problems[0]
    assert widget_rules.check_record({"finance_access_types":[]},rules)==[
        'Financial services: this is required. Fill it in on every row before saving.']
