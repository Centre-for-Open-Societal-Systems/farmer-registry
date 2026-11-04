"""Count the household head once when the roster lists the head twice.

A household's counts (size_of_group and the gender, child and elderly figures)
come from its member rows and its farmer rows. Entering a household requires the
head to be one of the member rows (is_head), and the head is usually also a
farmer of the household. The member form has no national id, so upstream's
roster, which keys a person by id when there is one and by name and birth date
otherwise, counted that person twice: a household of 3 came out as 4.

This module leaves the upstream roster file unchanged. install() wraps
union_roster_people so a member row that is a farmer already on the roster is
dropped before upstream counts. A member row is dropped only when it carries no
national id and either

* it is the head row (is_head, or relationship SELF) and the household has one
  farmer marked as its head, or
* its first name, last name and birth date (all three present) equal a farmer's.

A member row with its own id is never dropped here: the same id as a farmer is
merged by upstream already, and a different id is a different person. Each
farmer absorbs one member row, so two members are not both swallowed by one
farmer. Two different people with the same names and birth date, one of them
without an id, are indistinguishable from the head listed twice and are counted
once; the farmer extension offers no better key on a member row.
"""

import logging
import unicodedata
from datetime import date, datetime

_logger = logging.getLogger("oan-household-roster-head")

HEAD_RELATIONSHIP = "SELF"
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "`": "'", "´": "'"})


def _text(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        value = value.value
    text = unicodedata.normalize("NFKC", str(value)).translate(_APOSTROPHES)
    return " ".join(text.split()).casefold()


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "y"}
    return bool(value)


def _birth_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _active(person: dict) -> bool:
    status = person.get("record_status") or "ACTIVE"
    return _text(status) == "active"


def person_key(person: dict) -> str | None:
    """First name, last name and birth date, normalised; None unless all three are present."""
    first, last = _text(person.get("first_name")), _text(person.get("last_name"))
    born = _birth_date(person.get("birth_date"))
    if not (first and last and born):
        return None
    return f"{first}|{last}|{born.isoformat()}"


def is_head_row(member: dict) -> bool:
    return _truthy(member.get("is_head")) or _text(member.get("relationship_to_the_head")) == _text(
        HEAD_RELATIONSHIP
    )


def drop_listed_farmers(candidates: list[dict], farmers: list[dict]) -> list[dict]:
    """The candidate rows that are not a farmer of the roster listed a second time."""
    active = [farmer for farmer in farmers if _active(farmer)]
    head_farmers = [farmer for farmer in active if _truthy(farmer.get("is_household_head"))]
    head_farmer = head_farmers[0] if len(head_farmers) == 1 else None
    head_taken = False
    open_keys: dict[str, int] = {}
    for farmer in active:
        key = person_key(farmer)
        if key:
            open_keys[key] = open_keys.get(key, 0) + 1

    kept: list[dict] = []
    decided: dict[int, bool] = {}
    for person in candidates:
        if id(person) in decided:
            if decided[id(person)]:
                kept.append(person)
            continue
        keep = True
        if _active(person) and not _text(person.get("foundational_id")):
            key = person_key(person)
            if head_farmer is not None and not head_taken and is_head_row(person):
                head_taken, keep = True, False
                head_key = person_key(head_farmer)
                if head_key and open_keys.get(head_key):
                    open_keys[head_key] -= 1
            elif key and open_keys.get(key):
                open_keys[key] -= 1
                keep = False
        decided[id(person)] = keep
        if keep:
            kept.append(person)
    return kept


def install() -> bool:
    """Idempotent: upstream's union_roster_people ignores member rows that repeat a farmer."""
    try:
        from .openg2p_farmer.register_domain.services.utils import household_roster
    except ImportError:
        return False
    original = household_roster.union_roster_people
    if getattr(original, "_oan_head_once", False):
        return True

    def union_roster_people(members, farmers, *, overlay_person=None, overlay_household_id=None):
        candidates = list(members) + ([overlay_person] if overlay_person else [])
        kept = {id(person) for person in drop_listed_farmers(candidates, farmers)}
        return original(
            [member for member in members if id(member) in kept],
            farmers,
            overlay_person=overlay_person if overlay_person and id(overlay_person) in kept else None,
            overlay_household_id=overlay_household_id,
        )

    union_roster_people._oan_head_once = True
    household_roster.union_roster_people = union_roster_people
    _logger.info("Household roster counts the head listed as a member once")
    return True
