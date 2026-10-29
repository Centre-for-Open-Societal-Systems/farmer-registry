"""Values the registry derives from what was entered, never typed in.

The domain services apply these on every way in: the intake form and change
requests (validate_domain_attributes, pre_approve) and ingestion (post_ingest).
The previous farmer registry computed the same values with SQL backfills at
startup; here they are kept in step as records are saved.

This module has no database or framework imports, so it can be tested alone.
"""

import re
from collections.abc import Iterable
from datetime import date, datetime

from .ethiopian_calendar import gregorian_to_ethiopic_string

UNIT_TO_HECTARES = {
    "HECTARE": 1.0,
    "ACRE": 0.404686,
    "SQUARE_METER": 0.0001,
    "SQUARE_KM": 100.0,
    "SQUARE_FOOT": 0.0000092903,
    "SQUARE_YARD": 0.0000836127,
}

# geo_code_hierarchy_json level -> farmer column holding that level's name
GEO_NAME_FIELDS = {"region": "region_name", "zone": "zone_name", "woreda": "woreda_name", "kebele": "kebele_name"}


def _number(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).strip()).date()
    except ValueError:
        return None


def hectares(size, unit) -> float | None:
    """A land size in hectares; an unknown unit counts as hectares, as before."""
    size = _number(size)
    if size is None:
        return None
    return round(size * UNIT_TO_HECTARES.get(str(unit or "HECTARE"), 1.0), 6)


def land_rollup(lands: Iterable[tuple[str | None, float | None]]) -> dict:
    """A farmer's land totals from (ownership type, hectares) per active parcel.

    Owned is OWNER, rented is TENANT, and crop sharing is every other parcel.
    The farmer's land ownership is OWNER or TENANT when every typed parcel is
    that, HYBRID when they differ, and empty when no parcel has a type.
    """
    owned = rented = shared = total = 0.0
    kinds: set[str] = set()
    for kind, area in lands:
        area = area or 0.0
        total += area
        if kind == "OWNER":
            owned += area
        elif kind == "TENANT":
            rented += area
        else:
            shared += area
        if kind:
            kinds.add(kind)
    if not kinds:
        ownership = None
    elif len(kinds) == 1 and next(iter(kinds)) in ("OWNER", "TENANT"):
        ownership = next(iter(kinds))
    else:
        ownership = "HYBRID"
    return {
        "total_land_area": round(total, 6),
        "total_land_owned_area": round(owned, 6),
        "total_land_rent_area": round(rented, 6),
        "total_land_crop_sharing_area": round(shared, 6),
        "land_ownership": ownership,
    }


def geo_names(hierarchy) -> dict:
    """region_name .. kebele_name from the geo widget's hierarchy value."""
    levels = (hierarchy or {}).get("hierarchy") if isinstance(hierarchy, dict) else None
    names = dict.fromkeys(GEO_NAME_FIELDS.values())
    for level in levels or []:
        field = GEO_NAME_FIELDS.get(str(level.get("level_mnemonic") or "").lower())
        if field:
            names[field] = level.get("level_value_mnemonic") or None
    return names


def ethiopic_twin(record: dict, gc_field: str, ec_field: str) -> None:
    """Set a date's Ethiopian calendar twin from the Gregorian date.

    Dates are entered and stored in the Gregorian calendar with the registry's
    date widget, as OpenG2P does (its ODK forms show Ethiopian dates and still
    record the Gregorian one). The Ethiopian date is only derived, for lists,
    reports and the previous registry's data. A record without the Gregorian
    field, such as a partial update, is left alone.
    """
    if gc_field in record:
        record[ec_field] = ethiopic_of(record.get(gc_field))


def ethiopic_of(value) -> str | None:
    gregorian = _date(value)
    return gregorian_to_ethiopic_string(gregorian) if gregorian else None


# Ethiopian numbers: 9 national digits, mobile 9xx or 7xx, landline area codes.
ETHIOPIA_CALLING_CODE = "251"


def valid_country_code(code) -> bool:
    """A phone row's country: the 2-letter country code (ET) or the dialing
    code (+251, 251). The 3-letter ETH is neither."""
    text = str(code or "").strip()
    return bool(re.fullmatch(r"[A-Za-z]{2}|\+?[0-9]{1,4}", text))


def normalize_phone(number, country_code=None) -> tuple[str | None, str | None]:
    """(national number, E.164) for a phone number as typed.

    For Ethiopia (the default) +251 912 345 678, 0912345678 and 912345678 are
    one number, stored as its 9 national digits. Any other country's number is
    kept as typed, without spaces. A number that cannot be read returns
    (None, None).
    """
    raw = "".join(ch for ch in str(number or "") if ch.isdigit() or ch == "+")
    if not raw:
        return None, None
    country = str(country_code or "ET").upper()
    if country not in ("ET", "ETH", "251", "+251"):
        return raw, raw if raw.startswith("+") else None
    digits = raw.lstrip("+")
    digits = digits.removeprefix(ETHIOPIA_CALLING_CODE)
    digits = digits.removeprefix("0")
    if len(digits) != 9 or not digits.isdigit():
        return None, None
    return digits, f"+{ETHIOPIA_CALLING_CODE}{digits}"


# Languages written in Ethiopic (Ge'ez) script: the farmer's name in such a
# language must be in it. Names in other languages are kept as typed, as
# OpenG2P advises for names.
ETHIOPIC_SCRIPT_LANGUAGES = {"AMHARIC": "Amharic", "TIGRINYA": "Tigrinya"}
_ETHIOPIC_NAME = re.compile(r"^[ሀ-፿ⶀ-⷟꬀-꬯ ]+$")
LOCAL_NAME_LABELS = {
    "first_name_local": "First name",
    "middle_name_local": "Father's name",
    "last_name_local": "Grandfather's name",
}


def local_name_problems(record: dict) -> list[str]:
    """The farmer's own-language names without a language, or not in their
    language's script."""
    if "language_spoken" in record and not record.get("language_spoken") and any(
        str(record.get(field) or "").strip() for field in LOCAL_NAME_LABELS
    ):
        return [("Farmer's language: the name is entered in the farmer's language, but no language is chosen. "
                 "Choose the language it is written in.")]
    language = ETHIOPIC_SCRIPT_LANGUAGES.get(record.get("language_spoken") or "")
    if not language:
        return []
    return [
        f"{label} (farmer's language): {language} is written in Ethiopic (Ge'ez) script, and \"{value}\" is not. "
        "Type the name in Ge'ez letters, or choose the farmer's language again."
        for field, label in LOCAL_NAME_LABELS.items()
        if (value := str(record.get(field) or "").strip()) and not _ETHIOPIC_NAME.match(value)
    ]


# What a user types to find a farmer: the ids, and the names in each language
# (the middle name is the father's). search_text is indexed and matched as one
# string, so anything else (gender, education, dates, coordinates) is left to
# the list filters, as OpenG2P advises.
FARMER_SEARCH_FIELDS = (
    "functional_record_id", "foundational_id", "rid",
    "first_name", "middle_name", "last_name",
    "first_name_local", "middle_name_local", "last_name_local",
)


def farmer_search_text(payload: dict, extra=None) -> str:
    values = [*(extra or []), *(payload.get(field) for field in FARMER_SEARCH_FIELDS)]
    return " ".join(dict.fromkeys(str(v).strip() for v in values if v is not None and str(v).strip()))
