"""Values the form offers from Master Data, refused when they are not on the list.

The form offers gender, the farmer's language and marital status from Master
Data lists (GENDER, LANGUAGE, MARITAL_STATUS), and the location from the Master
Data geography. Core checks coded values only when its own switch is on, so a
request that carried another code, or a location id Master Data does not know,
was saved and later showed as a raw code. These checks run for every channel
from the Farmer's `validate_domain_attributes` (web save, change request,
validate, submit), and say which field, what is wrong and what to do.

Master Data is read through core's own client. When it cannot be read the
check is skipped with a warning, so an outage never blocks a save.

This module has no framework imports at load time, so it can be tested alone.
"""

import asyncio
import logging
import time

_logger = logging.getLogger("oan-coded-values")

# field -> (Master Data list, label key, English label when the key has no text)
CHOICES = {
    "gender": ("GENDER", "gender", "Gender"),
    "language_spoken": ("LANGUAGE", "farmers_language", "Farmer's language"),
    "marital_status": ("MARITAL_STATUS", "marital_status", "Marital status"),
}

_TTL_SECONDS = 300
MAX_LISTED = 10
_cache: dict = {}


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def choice_problems(record: dict, say, lists: dict[str, dict[str, str]]) -> list[str]:
    """One sentence per coded field of the record whose value is not on its list.

    `lists` maps a Master Data list to {code: text shown}; a list that is
    missing or empty cannot say what is wrong and is not judged.
    """
    problems = []
    for field, (attribute, label_key, label) in CHOICES.items():
        value = record.get(field)
        choices = lists.get(attribute)
        if _blank(value) or not choices or not isinstance(value, str):
            continue
        if value.strip() in choices:
            continue
        shown = [str(text) for text in choices.values()]
        listed = ", ".join(shown[:MAX_LISTED])
        if len(shown) > MAX_LISTED:
            listed += f" and {len(shown) - MAX_LISTED} more"
        problems.append(say("rule_choice", label=say.text(label_key, label), choices=listed))
    return problems


def fayda_problem(record: dict, say) -> str | None:
    """Has national ID answered Yes with no Fayda ID to show for it.

    A record that does not carry the Fayda ID at all (a partial change of an
    existing record) is not judged.
    """
    answer = record.get("has_national_id")
    yes = answer is True or (isinstance(answer, str) and answer.strip().lower() in ("true", "yes", "1"))
    if not yes or not _blank(record.get("foundational_id")):
        return None
    if "foundational_id" not in record and record.get("internal_record_id"):
        return None
    return say("rule_fayda_missing", label=say.text("has_national_id", "Has national ID"),
               fayda=say.text("foundational_id", "Fayda ID"))


def location_problem(record: dict, say, known: set[str] | None) -> str | None:
    """The kebele id (the lowest level the form picked) that Master Data does not know.

    `known` is the set of Master Data location ids, or None when it could not
    be read.
    """
    value = record.get("geo_lowest_level_value_id")
    if _blank(value) or not known:
        return None
    if str(value).strip() in known:
        return None
    return say("rule_location", label=say.text("farmer_geo_hierarchy", "Location"), value=str(value).strip())


def _client():
    from openg2p_registry_core.helpers.master_data import MasterDataClient

    return MasterDataClient.get_component() or MasterDataClient()


# Master Data is read for a person who is waiting. A read is given a few
# seconds; after the first failure the rest of the call is skipped, and the
# failure is remembered for a minute so the next saves do not each wait.
READ_SECONDS = 3.0
DOWN_SECONDS = 60.0
_down_until = 0.0


def _is_down() -> bool:
    return time.monotonic() < _down_until


def _mark_down(what: str, error) -> None:
    global _down_until
    _down_until = time.monotonic() + DOWN_SECONDS
    _logger.warning("%s skipped: Master Data could not be read in time (%s)", what, error or "timeout")


async def _fetch_lists(attributes, now) -> None:
    for attribute in attributes:
        hit = _cache.get(attribute)
        if hit and now < hit[0]:
            continue
        payload = await _client()._post(
            "/attributes/get_attribute_values", payload={"attribute_id": attribute},
            pagination={"current_page": 1, "page_size": 1000})
        rows = payload.get("attribute_values") if isinstance(payload, dict) else payload
        found = {row["value_code"]: row.get("value_display") or row["value_code"]
                 for row in rows or [] if isinstance(row, dict) and row.get("value_code")}
        _cache[attribute] = (now + _TTL_SECONDS, found)


async def master_data_lists(attributes) -> dict[str, dict[str, str]]:
    """{list: {code: text shown}} for the lists, from Master Data (cached five
    minutes). Lists that cannot be read are left out."""
    now = time.monotonic()
    if not _is_down():
        try:
            await asyncio.wait_for(_fetch_lists(attributes, now), READ_SECONDS)
        except Exception as error:  # includes the timeout
            _mark_down("Choice check", error)
    return {a: _cache[a][1] for a in attributes if a in _cache and now < _cache[a][0]}


async def known_location_ids() -> set[str] | None:
    """Every location id Master Data holds, or None when it cannot be read."""
    if _is_down():
        return None
    try:
        return set(await asyncio.wait_for(_client()._load_geo_index(), READ_SECONDS))
    except Exception as error:
        _mark_down("Location check", error)
        return None


async def coded_value_problems(records: list[dict], say) -> list[str]:
    """The problems of the Farmer records' Master Data values and Fayda answer."""
    problems = []
    wanted = {CHOICES[field][0] for record in records for field in CHOICES if not _blank(record.get(field))}
    lists = await master_data_lists(sorted(wanted)) if wanted else {}
    locate = any(not _blank(record.get("geo_lowest_level_value_id")) for record in records)
    known = await known_location_ids() if locate else None
    for record in records:
        problems += choice_problems(record, say, lists)
        for problem in (fayda_problem(record, say), location_problem(record, say, known)):
            if problem:
                problems.append(problem)
    return problems
