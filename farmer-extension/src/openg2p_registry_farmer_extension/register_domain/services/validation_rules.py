"""Single source of truth for the farmer-intake field rules (G2R-47, gaps G2/G3).

``widget-data-validation`` in the register metadata is enforced by the browser
only -- ``ui-widgets/src/utils/validation.ts`` runs it as the staff types. Every
other way a record reaches the register (bulk file import, the partner API,
ingestion) never loads that metadata, so a rule expressed only in the seed SQL
is not a rule about the data, just a rule about one UI.

This module restates those rules in Python so the domain services can apply them
on every path. The regexes are deliberately byte-identical to the metadata ones:
``tests/test_validation_rules_match_metadata.py`` reads the seed SQL and fails if
the two ever drift, which is the failure mode that actually matters -- a form
that accepts what the server rejects, or the reverse.

Rule provenance is the Gen1-parity decision signed off on G2R-26: replicate what
Gen1 enforced, not what would be nicer than Gen1.
"""

import re

# Latin plus Ethiopic (U+1200-U+137F), which covers Amharic and Oromo. The
# obvious regex borrowed from the platform reference is Latin + Devanagari and
# silently rejects valid Ethiopian names.
NAME_PATTERN = r"^[A-Za-z\u1200-\u137F][A-Za-z\u1200-\u137F\s'-]*$"
NAME_MAX_LENGTH = 100

# Gen2 splits the country out into its own column (defaulting to ETH), so this
# is the national significant number only: 9 digits, optionally trunk-prefixed
# with 0. Gen1 stored a single E.164 string, which is why migrated values have
# to be split rather than copied (G2R-26 Q2).
PHONE_PATTERN = r"^0?[1-9][0-9]{8}$"
PHONE_MAX_LENGTH = 10

# Tuned against the real Gen1 dump, where 22 of the 25 g2p_reg_id rows are a
# FAN- prefix plus 16 digits. The three that do not match are 5, 6 and 8 digits
# long ('56789', '348492', '76432345') and sit in a staging database whose
# farmers are named 'steve', 'test' and 'demo' -- so they read as junk rather
# than as a shorter legitimate format. If a production Gen1 database turns out
# to hold short values too, this bound is what has to move.
NATIONAL_ID_PATTERN = r"^(FAN-)?[0-9]{12,17}$"

# Per-ID-type value rules, keyed by IdTypeEnum member. This mapping exists
# because the client cannot express one: WidgetValidation declares `custom` and
# `zodSchema` but validation.ts implements neither, so the metadata gets a single
# pattern for the whole value column.
#
# Gen1's g2p_id_type holds exactly four rows -- UID, RID, "Farmer ODK ACK ID",
# "Member ODK ACK ID" -- and id_validation is NULL on every one of them, so Gen1
# enforced no format anywhere. The two ODK ACK types are deliberately absent from
# this mapping: their value is whatever the ODK submission carried
# (odk_client.py writes `json_data[id_value_key]` straight through), so there is
# no format to assert. A type not listed here is accepted.
#
# FAN is not a type. Every FAN- value in the Gen1 dump is filed under UID, which
# is why the prefix belongs in the pattern rather than the type list.
ID_TYPE_PATTERNS = {
    "UID": NATIONAL_ID_PATTERN,
    "RID": NATIONAL_ID_PATTERN,
}

# Gen1 parity: the farmer's first name (94% fill) and the father's first name.
# The father is captured as his own first/middle/last triple rather than
# standing in for the farmer's middle_name, which is therefore optional again.
# last_name holds the grandfather's name at 26%, birth_date is 10% and phone
# 13% -- requiring any of those would make the majority of genuine Gen1
# records impossible to save.
REQUIRED_NAME_FIELDS = ("first_name", "father_first_name")

NAME_FIELDS = (
    "first_name",
    "middle_name",
    "last_name",
    "first_name_amh",
    "middle_name_amh",
    "last_name_amh",
    "first_name_om",
    "middle_name_om",
    "last_name_om",
    "father_first_name",
    "father_middle_name",
    "father_last_name",
)

# Paths where a human is filling in a form and can be asked for a missing field.
# Bulk import and the partner API carry whatever the legacy record held, so
# required-checks are not applied to them: ~6% of Gen1 farmers have no first
# name at all, and rejecting them would block migration rather than improve it.
# Format checks still apply everywhere -- a malformed name is wrong on any path.
INTERACTIVE_IMPORT_SOURCES = {"INTAKE_FORM", "STAFF_PORTAL", "AGENT_PORTAL"}

_COMPILED: dict[str, re.Pattern] = {}


def _compiled(pattern: str) -> re.Pattern:
    if pattern not in _COMPILED:
        _COMPILED[pattern] = re.compile(pattern)
    return _COMPILED[pattern]


def matches(pattern: str, value) -> bool:
    """True when value satisfies pattern. Blank passes -- emptiness is a
    required-check concern, and conflating the two produces 'invalid format'
    on a field the user simply left alone."""
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    return bool(_compiled(pattern).match(text))


def is_interactive(record: dict) -> bool:
    """Whether this record came from someone filling in a form."""
    source = str(record.get("import_source") or "").strip().upper()
    # An absent import_source means the intake form did not set one; treat that
    # as interactive so a missing value fails closed rather than skipping the
    # check entirely.
    return not source or source in INTERACTIVE_IMPORT_SOURCES
