"""Build the farmer ODK form whose every choice list comes from Master Data.

    python odk/tools/build_mds_form.py --pack ../openg2p-data/packs/ETH-OAN         --geography <export of the environment's Master Data geography>

ODK Collect cannot read Master Data while a form is filled in, so the form
carries the lists at build time, exactly as Master Data serves them: the
choice names are the list's value codes (what the registry stores) and the
labels its displays. The registry's ODK transform then passes the codes
through unchanged, with no alias table between the form and the registry.

Taken from the v3 form (odk/tools/build_v3.py): every question, group, repeat,
relevance, constraint and translation. Replaced: the rows of every choice list
that is a Master Data list (the table below), and the region/zone/woreda/kebele
lists, which become the geography as external CSVs (name and code are the
level_value_id Master Data serves, which the web intake stores too; parent is
the parent's). Left as
they are: yes/no answers, consent, and the cooperative and union names, which
are not Master Data lists.

A translation (Amharic, Afaan Oromoo) is carried over from the v3 choice that
maps to the same code, by the registry's own mapping (odk/transform.py), so the
enumerator sees the wording they know; a code the old form never offered gets
the Master Data display in every language until a translation is added.

Geography belongs to each environment's Master Data, not to the pack: an
environment migrated from an older catalogue keeps its own unit ids (New Dev
serves region-ET01 ... kebele-ET010101101001). --geography takes a directory
with that catalogue's levels.json and values.json, in the pack's format, read
from the environment's Master Data (g2p_geo_levels, g2p_geo_level_values). It
defaults to the pack's own geography, for an environment seeded from the pack.
The CSVs must be rebuilt for each environment the form is published to.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import OrderedDict
from copy import copy
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "oan-extension/src"))
from oan_farmer_registry_extension.odk import transform  # noqa: E402

SOURCE = REPO / "odk/ATI_Farmers_Profile_ODK_Form_v3.xlsx"
TARGET = REPO / "odk/ATI_Farmers_Profile_ODK_Form_v4.xlsx"
MEDIA = REPO / "odk/media/mds"
LABELS = ("label::English (en)", "label::Amharic (am)", "label::Afaan Oromoo (om)")
LEVELS = ("region", "zone", "woreda", "kebele")

# XLSForm choice list -> (Master Data list, how a v3 choice name becomes a code, codes left out)
MDS_LISTS: dict[str, tuple[str, callable, set[str]]] = {
    "choices_gender": ("GENDER", lambda v: transform.code(v), set()),
    "choices_member_gender": ("GENDER", lambda v: transform.code(v), set()),
    "choices_language": ("LANGUAGE", lambda v: transform.code(v, transform.LANGUAGES), set()),
    "choices_farming_type": ("FARMING_TYPE", lambda v: transform.code(v, {"CROP_FARMING": "CROP", "LIVESTOCK_FARMING": "LIVESTOCK", "MIXED_FARMING": "MIXED"}), set()),
    "choices_marital_status": ("MARITAL_STATUS", lambda v: transform.code(v), set()),
    "choices_education_level": ("EDUCATION_LEVEL", lambda v: transform.code(v, {"READ_WRITE": "CAN_READ_AND_WRITE"}), set()),
    "choices_income_source": ("SOURCE_OF_INCOME", lambda v: transform.code(v, transform.INCOME), set()),
    "choices_primary_commodity": ("CROP_COMMODITY", lambda v: transform.code(v, transform.CROPS, "CROP_"), set()),
    "choices_crops_list": ("CROP_COMMODITY", lambda v: transform.code(v, transform.CROPS, "CROP_"), set()),
    "choices_farmer_role": ("FARMER_CLUSTER_ROLE", lambda v: transform.code(v), set()),
    "choices_land_ownership": ("LAND_OWNERSHIP_TYPE", lambda v: transform.code(v), set()),
    "oan_crop_season": ("CROP_SEASON", lambda v: transform.code(v, prefix="SEASON_"), set()),
    "choices_crop_water_source": ("WATER_SOURCE", lambda v: transform.code(v, transform.WATER), set()),
    "choices_livestock_water_source": ("WATER_SOURCE", lambda v: transform.code(v, transform.WATER), set()),
    "choices_livestocks": ("LIVESTOCK_TYPE", lambda v: transform.code(v, prefix="LSTK_"), set()),
    "choices_machinery": ("FARM_MACHINERY", lambda v: transform.code(v, transform.MACHINERY), set()),
    "choices_finance": ("FINANCE_ACCESS_TYPE", lambda v: transform.code(v), set()),
    "oan_identity_document_type": ("IDENTITY_DOCUMENT_TYPE", lambda v: transform.code(v), set()),
    # A member's relationship to the head; the head is never a member's answer.
    "choices_household_relationship": ("RELATIONSHIP_TO_HEAD", lambda v: transform.code(v, transform.RELATIONSHIP), {"SELF"}),
}


def read_lists(pack: Path) -> dict[str, dict]:
    lists = {}
    for folder in (pack / "codelists", pack / "domains"):
        for path in sorted(folder.rglob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "attribute_id" in data:
                lists[data["attribute_id"]] = data
    return lists


def read_values(pack: Path) -> dict[str, list[dict]]:
    levels = {level["level_id"]: level["level_mnemonic"] for level in json.loads((pack / "levels.json").read_text(encoding="utf-8"))}
    units: dict[str, list[dict]] = {level: [] for level in LEVELS}
    for value in json.loads((pack / "values.json").read_text(encoding="utf-8")):
        level = levels[value["level_id"]]
        if level in units:
            units[level].append(value)
    return units


def choice_rows(old_rows: list[dict], mds_list: dict, to_code, left_out: set[str]) -> tuple[list[dict], dict]:
    """The list's rows as Master Data has them, with the old translations."""
    carried = {}
    for row in old_rows:
        try:
            mapped = to_code(row["name"])
        except Exception:
            mapped = None
        if mapped:
            carried.setdefault(mapped, row)
    rows, report = [], {"codes": 0, "translated": 0, "dropped_choices": []}
    for value in sorted(mds_list["values"], key=lambda v: (v.get("sort_order") or 0, v["value_code"])):
        code = value["value_code"]
        if code in left_out:
            continue
        old = carried.get(code)
        labels = {LABELS[0]: value["value_display"]}
        for label in LABELS[1:]:
            labels[label] = old.get(label) if old and old.get(label) else value["value_display"]
        rows.append({"name": code, **labels})
        report["codes"] += 1
        report["translated"] += bool(old)
    report["dropped_choices"] = sorted(str(r["name"]) for r in old_rows if to_code(r["name"]) not in {v["value_code"] for v in mds_list["values"]})
    return rows, report


def write_media(units: dict[str, list[dict]], media: Path) -> dict[str, int]:
    media.mkdir(parents=True, exist_ok=True)
    counts = {}
    for level in LEVELS:
        path = media / f"{level}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["name", "label", "code", "parent"])
            for unit in sorted(units[level], key=lambda u: u["level_value_id"]):
                parent = unit.get("parent_level_value_id") or ""
                writer.writerow([unit["level_value_id"], unit["display_name"], unit["level_value_id"],
                                 parent if level != "region" else ""])
        counts[level] = len(units[level])
    return counts


def build(source: Path, pack: Path, target: Path, media: Path, version: str,
          geography: Path | None = None) -> dict:
    lists = read_lists(pack)
    book = openpyxl.load_workbook(source)
    choices = book["choices"]
    header = [cell.value for cell in choices[1]]
    column = {key: index + 1 for index, key in enumerate(header) if key}
    rows = [{header[i]: cell.value for i, cell in enumerate(row) if header[i] is not None and cell.value is not None}
            for row in choices.iter_rows(min_row=2)]
    rows = [row for row in rows if row.get("list_name")]
    report = OrderedDict()
    kept: list[dict] = []
    replaced: dict[str, list[dict]] = {}
    for row in rows:
        name = row["list_name"]
        if name in MDS_LISTS or name == "choices_region":
            replaced.setdefault(name, []).append(row)
        else:
            kept.append(row)
    for name, (attribute_id, to_code, left_out) in MDS_LISTS.items():
        if attribute_id not in lists:
            raise SystemExit(f"{attribute_id}: not in the pack")
        new_rows, info = choice_rows(replaced.get(name, []), lists[attribute_id], to_code, left_out)
        report[name] = {"master_data_list": attribute_id, **info}
        for new in new_rows:
            kept.append({"list_name": name, **new})
    # The region list leaves the form: the four levels are external lists.
    report["choices_region"] = {"master_data_list": "geo hierarchy (region.csv)", "codes": 0}
    style = [copy(choices.cell(2, c)._style) for c in range(1, choices.max_column + 1)]
    choices.delete_rows(2, choices.max_row)
    for index, row in enumerate(kept, start=2):
        for c in range(1, len(style) + 1):
            choices.cell(index, c)._style = copy(style[c - 1])
        for key, value in row.items():
            if key in column:
                choices.cell(index, column[key], value)
    survey = book["survey"]
    survey_columns = {cell.value: cell.column for cell in survey[1] if cell.value}
    for row in range(2, survey.max_row + 1):
        kind = survey.cell(row, survey_columns["type"]).value
        if isinstance(kind, str) and kind.startswith("select_one choices_region"):
            survey.cell(row, survey_columns["type"], "select_one_from_file region.csv")
    settings = book["settings"]
    settings_columns = {cell.value: cell.column for cell in settings[1] if cell.value}
    settings.cell(2, settings_columns["version"], version)
    target.parent.mkdir(parents=True, exist_ok=True)
    book.save(target)
    geography = geography or pack
    counts = write_media(read_values(geography), media)
    return {"source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "pack": str(pack), "geography": str(geography), "pack_version": json.loads((pack / "manifest.json").read_text(encoding="utf-8")).get("version"),
            "output": str(target), "version": version, "media": {level: f"{media / level}.csv" for level in LEVELS},
            "units": counts, "lists": report}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pack", required=True, type=Path, help="the country pack (packs/ETH-OAN of openg2p-data)")
    parser.add_argument("--geography", type=Path, default=None,
                        help="levels.json + values.json of the target environment's Master Data geography (default: the pack's)")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--out", type=Path, default=TARGET)
    parser.add_argument("--media", type=Path, default=MEDIA)
    parser.add_argument("--version", default="2026.10.28")
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.pack, args.out, args.media, args.version, args.geography), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
