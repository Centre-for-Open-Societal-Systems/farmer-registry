"""Tests for the OAN wording of the farmer extension's check messages.

    uv run --no-project --with pytest pytest oan-extension/tests
"""

import ast
import importlib.util
import re
from pathlib import Path

_ROOT = Path(__file__).parents[2]
_PATH = Path(__file__).parents[1] / "src/oan_farmer_registry_extension/register_domain/services/upstream_messages.py"
_spec = importlib.util.spec_from_file_location("upstream_messages", _PATH)
upstream_messages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(upstream_messages)
reword = upstream_messages.reword


def test_core_attribute_choice_names_field_and_fix():
    text = "record 0: gender='unknown' is not a value of GENDER (permitted: FEMALE, MALE)"
    assert reword(text, {"gender": "Gender"}) == 'Gender: "unknown" is not one of the choices. Pick one from the list.'


def test_core_attribute_problems_join_without_splitting_quoted_values():
    text = (
        "record 0: gender='bad; choice' is not a value of GENDER (permitted: FEMALE, MALE); "
        'record 1: education_level="not valid" is not a value of EDUCATION_LEVEL (permitted: PRIMARY)'
    )
    assert reword(text, {"gender": "Gender", "education_level": "Education Level"}) == (
        'Gender: "bad; choice" is not one of the choices. Pick one from the list.; '
        'Education Level: "not valid" is not one of the choices. Pick one from the list.'
    )


def test_core_missing_master_data_is_actionable():
    text = "Attribute validation is enabled, but Master Data has no attribute values configured"
    assert reword(text) == upstream_messages.MDS_UNAVAILABLE
    assert "Retry" in reword(text) and "support" in reword(text)


def test_core_mds_transport_failure_does_not_expose_transport_details():
    text = "Master Data API request failed: /attributes/get_attribute_values (HTTP 503)"
    assert reword(text) == upstream_messages.MDS_UNAVAILABLE


def test_core_choice_message_uses_translation():
    text = "record 0: gender='unknown' is not a value of GENDER (permitted: MALE)"
    assert reword(text, {"gender": "Gender", "upstream_mds_option": "{label}: select a listed value instead of {value}."}) == (
        "Gender: select a listed value instead of unknown.")

# Upstream messages that already say what to do, so they are not reworded.
ALREADY_EXPLAINED = (
    "were entered; the members must match the size of the group",
    "update the members or the size so they match",
    "add every member of the household, including the head",
    "(select the land in the row)",
    "is not a phone number",
)


def _upstream_messages():
    """Every message the farmer extension passes to validation_error, with
    each f-string placeholder filled by a sample value."""
    for path in (_ROOT / "farmer-extension/src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "validation_error" and node.args):
                continue
            yield path.name, _text(node.args[0])


def _text(node) -> str:
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.JoinedStr):
        return "".join(str(v.value) if isinstance(v, ast.Constant) else "head_count" for v in node.values)
    if isinstance(node, ast.BinOp):
        return _text(node.left) + _text(node.right)
    return "head_count"


def test_every_upstream_message_is_reworded_or_already_says_what_to_do():
    unexplained = [
        (name, message) for name, message in _upstream_messages()
        if reword(message) == message and not any(hint in message for hint in ALREADY_EXPLAINED)
    ]
    assert unexplained == []


def test_a_reworded_message_names_the_field_and_the_fix():
    assert reword("birth_date must not be in the future") == (
        "Birth Date: the date is in the future. Enter the real birth date, today or earlier.")


def test_a_field_named_in_the_message_is_shown_by_its_label():
    words = {"head_count": "Head Count"}
    assert reword("head_count must not be negative", words) == "Head Count: must not be negative. Enter 0 or more."
    assert reword("gender must be one of FEMALE, MALE", {"gender": "Gender"}) == (
        "Gender: not one of the choices. Pick one from the list.")


def test_missing_household_fields_are_listed_by_label():
    words = {"size_of_group": "Household Size", "headship_type": "Headship Type"}
    assert reword("Required household fields missing: size_of_group, headship_type", words) == (
        "Household: Household Size, Headship Type are empty. Fill them in before submitting.")


def test_a_language_rewords_by_key():
    words = {"upstream_land_size": "Land Size: enter more than 0"}
    assert reword("land_size must be greater than zero when provided", words) == "Land Size: enter more than 0"


def test_an_unknown_message_is_left_as_it_is():
    assert reword("Something else went wrong; try again") == "Something else went wrong; try again"


def test_every_entry_has_a_unique_key_and_a_valid_pattern():
    keys = [key for key, _, _ in upstream_messages.REWORDED]
    assert len(keys) == len(set(keys))
    for _, pattern, _ in upstream_messages.REWORDED:
        re.compile(pattern)


def test_the_member_count_message_keeps_its_numbers():
    assert reword("Members entered: 2 male / 1 female, but the household says 1 male / 2 female") == (
        "Household Members: 2 male and 1 female are entered, but the household says 1 male and 2 female. "
        "Correct the members' gender or the household's counts so they match.")
