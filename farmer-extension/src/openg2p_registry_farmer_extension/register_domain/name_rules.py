"""The rule for a person's name, applied on the server for every source.

A name is 1 to 100 characters: letters (any script, Ge'ez included), combining
marks, spaces, apostrophes and hyphens, with at least one letter. The staff UI
applies the same rule from the name widgets' `widget-data-validation`
(meta_data/zz-oan/19_name_rules.sql); this module covers what has no browser:
ODK submissions, partner messages and API change requests.

The Crop register refuses any other name, so Farmer must not accept one that
would break enrichment. Registers cannot import each other's code, so the rule
is kept here, character for character as Crop applies it.

This module has no database or framework imports, so it can be tested alone.
"""

import unicodedata

MAX_LENGTH = 100

# field -> the name as the form calls it
NAME_LABELS = {
    "first_name": "First Name",
    "middle_name": "Father's Name",
    "last_name": "Grandfather's Name",
    "first_name_local": "First Name (own language)",
    "middle_name_local": "Father's Name (own language)",
    "last_name_local": "Grandfather's Name (own language)",
}

MESSAGE = "{label}: use letters only (spaces, apostrophes and hyphens allowed)"
MESSAGE_TOO_LONG = "{label}: too long. Enter at most {max} characters"


def name_issue(value) -> str | None:
    """"letters" or "length" when the name breaks the rule, else None."""
    if not isinstance(value, str):
        return "letters"
    cleaned = unicodedata.normalize("NFC", value.strip())
    if len(cleaned) > MAX_LENGTH:
        return "length"
    if (
        not cleaned
        or not any(char.isalpha() for char in cleaned)
        or any(
            not unicodedata.category(char).startswith(("L", "M")) and char not in " '-\u2019"
            for char in cleaned
        )
    ):
        return "letters"
    return None


def name_problems(record: dict, labels: dict[str, str] = NAME_LABELS) -> list[str]:
    """One sentence per name in the record that breaks the rule.

    Only names that are present are checked; whether a name is required is the
    form's rule, not this one.
    """
    problems = []
    for field, label in labels.items():
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        issue = name_issue(value)
        if issue == "length":
            problems.append(MESSAGE_TOO_LONG.format(label=label, max=MAX_LENGTH))
        elif issue:
            problems.append(MESSAGE.format(label=label))
    return problems
