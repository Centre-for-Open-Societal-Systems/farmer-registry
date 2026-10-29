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
        problems.append(say("rule_choice", label=say.text(label_key, label),
                            choices=", ".join(str(text) for text in choices.values())))
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


async def master_data_lists(attributes) -> dict[str, dict[str, str]]:
    """{list: {code: text shown}} for the lists, from Master Data (cached five
    minutes). A list that cannot be read is left out."""
    now = time.monotonic()
    lists = {}
    for attribute in attributes:
        hit = _cache.get(attribute)
        if hit and now < hit[0]:
            lists[attribute] = hit[1]
            continue
        try:
            payload = await _client()._post(
                "/attributes/get_attribute_values", payload={"attribute_id": attribute},
                pagination={"current_page": 1, "page_size": 1000})
        except Exception as error:
            _logger.warning("Choice check skipped for %s: Master Data could not be read (%s)", attribute, error)
            continue
        rows = payload.get("attribute_values") if isinstance(payload, dict) else payload
        found = {row["value_code"]: row.get("value_display") or row["value_code"]
                 for row in rows or [] if isinstance(row, dict) and row.get("value_code")}
        _cache[attribute] = (now + _TTL_SECONDS, found)
        lists[attribute] = found
    return lists


async def known_location_ids() -> set[str] | None:
    """Every location id Master Data holds, or None when it cannot be read."""
    try:
        return set(await _client()._load_geo_index())
    except Exception as error:
        _logger.warning("Location check skipped: Master Data could not be read (%s)", error)
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
