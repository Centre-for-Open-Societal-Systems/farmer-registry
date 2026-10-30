"""The name each Farmer register row is shown by, composed from what the row holds.

record_name is the title of a record in the header, the register lists, the
change request lists and the history. The platform stores it as text when the
row is saved and has no Master Data lookup at that point, so child rows would
otherwise be named after raw codes ("CROP_TEFF SEASON_MEHER"). Here a code is
turned into words (prefix removed, underscores to spaces, capitalised), and a
value that is already text (a cooperative's name) is kept as typed. The text
Master Data shows for a code can differ from this wording (a commodity
labelled "Teff for testing" is named "Teff"); the platform gives a name
generator no way to read that label.

This module has no database or framework imports, so it can be tested alone.
"""

import re
from decimal import Decimal, InvalidOperation

# field -> prefix its codes carry in Master Data lists
CODE_PREFIXES = {
    "commodity": "CROP_",
    "season": "SEASON_",
    "livestock_type": "LSTK_",
    "breed": "BREED_",
}

_CODE = re.compile(r"^[A-Z0-9_]+$")


def _text(value) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def words(value, prefix: str = "") -> str:
    """A code as words ("CROP_FABA_BEAN" -> "Faba Bean"); any other text unchanged."""
    text = _text(value)
    if not _CODE.match(text):
        return text
    if prefix and text.startswith(prefix) and len(text) > len(prefix):
        text = text[len(prefix):]
    return " ".join(part.capitalize() for part in text.split("_") if part)


def _field(payload: dict, key: str) -> str:
    return words(payload.get(key), CODE_PREFIXES.get(key, ""))


def _size(value) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        number = Decimal(text)
    except InvalidOperation:
        return text
    if not number.is_finite():
        return text
    return format(number.normalize(), "f")


def _join(parts, separator=" ") -> str:
    return separator.join(part for part in parts if part)


def farmer(payload: dict) -> str:
    return _join(_text(payload.get(key)) for key in ("first_name", "middle_name", "last_name"))


def land(payload: dict) -> str:
    size = _join([_size(payload.get("land_size")), _field(payload, "unit")])
    return _join([size, _field(payload, "current_land_use")], ", ")


def crop(payload: dict) -> str:
    return _join([_field(payload, "commodity"), _field(payload, "season")], ", ")


def livestock(payload: dict) -> str:
    kind, breed = _field(payload, "livestock_type"), _field(payload, "breed")
    return f"{kind} ({breed})" if kind and breed else kind or breed


def phone(payload: dict) -> str:
    return _join([_field(payload, "phone_type"), _text(payload.get("phone_number"))])


def membership(payload: dict) -> str:
    named = _text(payload.get("primary_cooperative_name")) or _text(payload.get("cooperative_union_name"))
    if named:
        return named
    role = _field(payload, "farmer_cluster_role")
    return f"Farmer cluster, {role}" if role else ""


_INPUTS = (
    ("fertilizer_use", "fertilizer"),
    ("pesticide_use", "pesticide"),
    ("insecticide_use", "insecticide"),
    ("improved_seed_use", "improved seed"),
)


def farm_inputs(payload: dict) -> str:
    """"Farm inputs" with what was used: the farm inputs row has no link to a land."""
    used = [label for key, label in _INPUTS if payload.get(key) in (True, "true", "True", "TRUE", 1)]
    water = _field(payload, "water_source")
    detail = _join([*used, f"water: {water}" if water else ""], ", ")
    return f"Farm inputs ({detail})" if detail else ""


# Columns each composer reads
FIELDS = {
    "Farmer": ("first_name", "middle_name", "last_name"),
    "Land": ("land_size", "unit", "current_land_use"),
    "Crop": ("commodity", "season"),
    "Livestock": ("livestock_type", "breed"),
    "MembershipDetails": ("primary_cooperative_name", "cooperative_union_name", "farmer_cluster_role"),
    "FarmInputs": ("fertilizer_use", "pesticide_use", "insecticide_use", "improved_seed_use", "water_source"),
    "FarmerPhone": ("phone_type", "phone_number"),
}

COMPOSERS = {
    "Farmer": farmer,
    "Land": land,
    "Crop": crop,
    "Livestock": livestock,
    "MembershipDetails": membership,
    "FarmInputs": farm_inputs,
    "FarmerPhone": phone,
}


def compose(mnemonic: str, payload: dict) -> str:
    """The readable name of a row of the register, or "" when it holds nothing to name it by."""
    composer = COMPOSERS.get(mnemonic)
    return composer(payload).strip() if composer else ""


def readable_name(mnemonic: str, payload: dict, value):
    """The name to store for a row being given `value` as its record name.

    The composed name replaces `value`. An intake form's name carries the
    application reference core appends; it is kept when `value` had it.
    """
    name = compose(mnemonic, payload)
    if not name:
        return value
    reference = _text(payload.get("application_reference"))
    if reference and reference in _text(value) and reference not in name:
        name = f"{name} {reference}"
    return name


def renamed_search_text(search_text, old_name, new_name):
    """The search text of a row after its record name changed.

    Core builds search_text from the record name, so the old name is replaced
    by the new one; a search text that does not hold the old name gets the new
    one appended. A row without search text is left without.
    """
    if not search_text:
        return search_text
    old = _text(old_name)
    if old and old in search_text:
        return search_text.replace(old, new_name, 1)
    return f"{search_text} {new_name}"
