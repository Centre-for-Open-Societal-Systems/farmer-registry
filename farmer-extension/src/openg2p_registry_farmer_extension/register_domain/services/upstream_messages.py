"""Upstream's domain check messages, said the OAN way.

The farmer extension's checks state the rule ("birth_date must not be in the
future") with the field's database name. OAN's messages name the field as the
form shows it and say what to enter instead, so each known upstream message is
matched here and reworded. The farmer extension itself is not changed.

Each entry is a translation key, the pattern of the upstream message and the
English text. A language rewords a message by translating its key; {1}, {2}
are the pattern's groups and {label} the label of a field the message names.
A message with no entry, which already says what to do, is left as it is.

This module has no database or framework imports, so it can be tested alone.
"""

import ast
import re

MDS_UNAVAILABLE = "Reference choices are unavailable. Try again in a few minutes, or contact support if it continues."

REWORDED: list[tuple[str, str, str]] = [
    ("upstream_mds_unavailable",
     r"(?:Attribute validation is enabled, but Master Data has no attribute values configured|Master Data API request failed: .+)",
     MDS_UNAVAILABLE),
    ("upstream_birth_date_future", r"birth_date must not be in the future",
     "Birth date: the date is in the future. Enter the real birth date, today or earlier."),
    ("upstream_planted_date_future", r"planted_date must not be in the future",
     "Planted date: the date is in the future. Enter the day the crop was planted, today or earlier."),
    ("upstream_year_of_acquisition_future", r"year_of_acquisition must not be in the future",
     "Year of acquisition: the year is in the future. Enter the year the land was acquired."),
    ("upstream_age_birth_date", r"estimated_age must be consistent with birth_date within one year",
     ("Estimated age: does not match the birth date. Correct the age to within a year of the "
     "birth date, or clear one of the two.")),
    ("upstream_land_size", r"land_size must be greater than zero when provided",
     "Land size: must be more than 0. Enter the land's area, for example 0.5, or leave it empty."),
    ("upstream_poverty_score", r"poverty_score must be between 0 and 100 when provided",
     "Poverty score: must be from 0 to 100. Enter a score in that range or leave it empty."),
    ("upstream_size_of_group", r"size_of_group must be at least 1",
     "Size of group: must be at least 1. Count the head and every member living in the household."),
    ("upstream_children", r"number_of_children must be between 0 and size_of_group",
     "Number of children: must be from 0 up to the size of group. Correct the count or the size."),
    ("upstream_elderly", r"number_of_elderly_members must be between 0 and size_of_group",
     "Number of elderly members: must be from 0 up to the size of group. Correct the count or the size."),
    ("upstream_male_female", r"number_of_male_members \+ number_of_female_members must not exceed size_of_group",
     ("Male and female members: together they are more than the size of group. Correct the counts "
     "or the size.")),
    ("upstream_no_head", r"One household member must be marked as the head \(is_head\)",
     "Household members: no member is marked as the head. Tick Head of household for the head."),
    ("upstream_two_heads", r"Only one household member can be marked as the head \(is_head\)",
     "Household members: more than one member is marked as the head. Tick Head of household for one member only."),
    ("upstream_relationship_missing", r"relationship_to_the_head is required for every member who is not the head",
     "Relationship to the head: missing for a member who is not the head. Pick it for every other member."),
    ("upstream_relationship_self", r"relationship_to_the_head SELF is reserved for the head; tick is_head instead",
     ("Relationship to the head: Self is only for the head. Tick Head of household for that member, or pick "
     "their relationship.")),
    ("upstream_relationship_option", r"relationship_to_the_head must be one of (.+)",
     "Relationship to the head: not one of the choices. Pick one from the list."),
    ("upstream_other_land_owner", r"other_land_owner must be Yes or No",
     "Other land owner: answer Yes or No."),
    ("upstream_duplicate_commodity", r"Duplicate commodity entries are not allowed",
     "Crops: the same crop is listed twice. Keep one row per crop and remove the other."),
    ("upstream_duplicate_livestock", r"Duplicate livestock_type entries are not allowed",
     "Livestock: the same livestock type is listed twice. Keep one row per type and add up the head count."),
    ("upstream_household_missing", r"Household information must be entered before the submission can be finalized",
     "Household: the household information is empty. Fill it in before submitting."),
    ("upstream_members_missing", r"Household members must be entered before the submission can be finalized",
     "Household members: none are entered. Add every member, including the head, before submitting."),
    ("upstream_household_fields", r"Required household fields missing: (.+)",
     "Household: {fields} are empty. Fill them in before submitting."),
    ("upstream_member_genders", r"Members entered: (\S+) male / (\S+) female, but the household says (\S+) male / (\S+) female",
     ("Household members: {1} male and {2} female are entered, but the household says {3} male and {4} "
     "female. Correct the members' gender or the household's counts so they match.")),
    ("upstream_option", r"(\w+) must be one of (.+)",
     "{label}: not one of the choices. Pick one from the list."),
    ("upstream_whole_number", r"(.+?) must be a whole number",
     "{label}: is not a whole number. Enter digits only, for example 12."),
    ("upstream_negative", r"(.+?) must not be negative",
     "{label}: must not be negative. Enter 0 or more."),
]

_COMPILED = [(key, re.compile(pattern), text) for key, pattern, text in REWORDED]
_MDS_OPTION = re.compile(
    r'''record \d+: (\w+)=('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*") is not a value of (\S+) \(permitted: [^)]*\)''')


def _label(name: str, messages: dict[str, str]) -> str:
    name = name.strip()
    found = messages.get(name)
    return found if isinstance(found, str) and found else name


def reword(message: str, messages: dict[str, str] | None = None) -> str:
    """The OAN wording of one upstream message, or the message unchanged."""
    messages = messages or {}
    # Core joins independently generated problems with '; '. Parse its quoted
    # repr values before splitting, so punctuation inside a value is preserved.
    core_message = message.strip()
    parts, end = [], 0
    for match in _MDS_OPTION.finditer(core_message):
        if core_message[end:match.start()] not in ("", "; "):
            break
        field, quoted, _ = match.groups()
        value = ast.literal_eval(quoted)
        english = '{label}: "{value}" is not one of the choices. Pick one from the list.'
        template = messages.get("upstream_mds_option") or english
        try:
            parts.append(template.format(label=_label(field, messages), value=value))
        except (AttributeError, IndexError, KeyError, ValueError):
            parts.append(english.format(label=_label(field, messages), value=value))
        end = match.end()
    if parts and end == len(core_message):
        return "; ".join(parts)
    for key, pattern, english in _COMPILED:
        match = pattern.fullmatch(message.strip())
        if not match:
            continue
        template = messages.get(key) if isinstance(messages.get(key), str) and messages.get(key) else english
        groups = match.groups()
        params = {
            "label": _label(groups[0], messages) if groups else "",
            "fields": ", ".join(_label(f, messages) for f in groups[0].split(",")) if groups else "",
        }
        try:
            return template.format(*([match.group(0), *groups]), **params)
        except (IndexError, KeyError, ValueError):
            return english.format(*([match.group(0), *groups]), **params)
    return message
