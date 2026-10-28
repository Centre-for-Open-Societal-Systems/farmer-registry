#!/usr/bin/env python3
"""Build the farmer form's location lists from the shared location hierarchy.

The form picks region from the XLSForm choices sheet and zone > woreda >
kebele from external CSV lists. External lists avoid duplicating thousands of
translated XML labels in the form model. All four levels are generated from
odk/legacy-geo/ethiopia_geo_seed.sql.gz, the COSS Ethiopia hierarchy the
registry's Master Data is seeded with (region-ET04, zone-ET0408,
woreda-ET040801, kebele-ET040801101001), so every place Master Data knows is
offered, under its Master Data name and parent, and nothing else.

The codes are the P-codes as numbers, as the form has always stored them
(region 4, zone 408, woreda 40801, kebele 40801101001). farmer_transform.j2
pads the kebele back to kebele-ET040801101001 (or a woreda picked with an
"other" kebele to woreda-ET040801) and sends it as geo_lowest_level_value_id;
the farmer service fills the names from Master Data. The region number also
filters the cooperative and union lists (PrimaryCoopList.csv,
choices_name_union).

Region labels keep their Amharic and Afaan Oromoo translations; zone, woreda
and kebele names have none in the hierarchy, so all three label columns carry
the Master Data name, as before.

    python odk/build_location_media.py          # rewrite the lists
    python odk/build_location_media.py --check  # exit 1 if they are stale

tests/unit/test_odk_location_media.py runs the check. Publish the rebuilt XLSForm and
media together as a new version of the same form. Audit Master Data compatibility
separately before enabling Registry ingestion.
"""

from __future__ import annotations

import csv
import io
import gzip
import re
from collections import Counter
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
SOURCE = REPO / "odk/legacy-geo/ethiopia_geo_seed.sql.gz"
FORM = HERE / "ATI_Farmers_Profile_ODK_Form_v2.xlsx"
KEBELES = HERE / "media" / "KebeleList.csv"
ZONES = HERE / "media" / "ZoneList.csv"
WOREDAS = HERE / "media" / "WoredaList.csv"

LOCATION_LISTS = ("choices_region", "choices_zone", "choices_woreda")
LABELS = ("label::English (en)", "label::Amharic (am)", "label::Afaan Oromoo (om)")
# The form's own escape hatches, kept as they are.
OTHER_KEBELE = ["other", "Other", "other_kebele"]


def load_hierarchy(source: pathlib.Path = SOURCE) -> dict[str, dict[str, tuple[str, str | None]]]:
    """{level: {code: (name, parent code)}}, codes as P-code digits ("0408")."""
    levels: dict[str, dict[str, tuple[str, str | None]]] = {"region": {}, "zone": {}, "woreda": {}, "kebele": {}}
    rows = []
    # Read only the checked-in seed's INSERT literals; never execute SQL here.
    text = gzip.decompress(source.read_bytes()).decode("utf-8")
    pattern = re.compile(r"INSERT INTO public\.g2p_geo_level_values \(([^)]+)\) VALUES \((.*)\) ON CONFLICT \(level_value_id\) DO NOTHING;")
    token = re.compile(r"'(?:[^']|'')*'|NULL")
    for line in text.splitlines():
        if not line.startswith("INSERT INTO public.g2p_geo_level_values "):
            continue
        match = pattern.fullmatch(line)
        if not match:
            raise ValueError("Unsupported geography seed INSERT")
        columns = [c.strip() for c in match[1].split(',')]
        literals, end = [], 0
        for value in token.finditer(match[2]):
            if match[2][end:value.start()].strip() != ("," if literals else ""):
                raise ValueError("Unsupported geography seed value")
            literal = value.group()
            literals.append(None if literal == "NULL" else literal[1:-1].replace("''", "'"))
            end = value.end()
        if match[2][end:].strip() or len(literals) != len(columns):
            raise ValueError("Incomplete geography seed row")
        rows.append(dict(zip(columns, literals)))
    if not rows:
        raise ValueError("No geography rows found")
    # Match the RC MDS override: distinct places with duplicate sibling labels
    # retain their P-codes in the displayed label instead of dropping a place.
    names = Counter((r['level_id'], r['parent_level_value_id'], r['level_value_mnemonic']) for r in rows)
    for row in rows:
        level = row["level_id"].removeprefix("level-")
        code = row["level_value_id"].split("-ET", 1)[1]
        parent = row.get("parent_level_value_id")
        name = row['level_value_mnemonic'].strip()
        if names[(row['level_id'], parent, row['level_value_mnemonic'])] > 1:
            name += ' (' + row['level_value_id'].split('-', 1)[1] + ')'
        if code in levels[level]:
            raise ValueError("Duplicate location code: " + code)
        levels[level][code] = (name, parent.split("-ET", 1)[1] if parent else None)
    parent_levels = {'region': None, 'zone': 'region', 'woreda': 'zone', 'kebele': 'woreda'}
    widths = {'region': 2, 'zone': 4, 'woreda': 6, 'kebele': 12}
    for level, values in levels.items():
        for code, (name, parent) in values.items():
            # The supplied catalog includes one seven-digit woreda P-code.
            # Keep the official source ID; the transform handles its numeric
            # XLSForm representation explicitly rather than truncating it.
            exceptional = level == 'woreda' and code == '0420112'
            if not code.isdigit() or (len(code) != widths[level] and not exceptional) or not name:
                raise ValueError("Invalid location code/label: " + code)
            parent_level = parent_levels[level]
            if (parent_level and parent not in levels[parent_level]) or (not parent_level and parent):
                raise ValueError("Missing location parent: " + code)
    return levels


def number(code: str) -> int:
    return int(code)


def choice_rows(levels, region_translations: dict[int, tuple[str, str]]) -> list[dict]:
    """Only regions stay inline; pyxform also emits unused choice lists."""
    rows = []
    for code, (name, _) in sorted(levels["region"].items(), key=lambda kv: kv[1][0].lower()):
        am, om = region_translations.get(number(code), (name, name))
        rows.append({"list_name": "choices_region", "name": number(code), "labels": (name, am, om)})
    return rows


def kebele_csv(levels) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    # Only carry columns used by the itemset. Redundant ancestors and list_name
    # used to create ~60,000 unnecessary XML nodes in each Enketo form model.
    writer.writerow(["name", "label", "woreda"])
    for code, (name, woreda) in sorted(levels["kebele"].items(), key=lambda kv: (kv[1][1], kv[1][0].lower(), kv[0])):
        writer.writerow([number(code), name, number(woreda)])
    writer.writerow(OTHER_KEBELE)
    return buffer.getvalue()


def parent_csv(levels, level):
    if level not in ("zone", "woreda"):
        raise ValueError("Only external zone/woreda lists are supported")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["name", "label", "region" if level == "zone" else "zone"])
    for code, (name, parent) in sorted(levels[level].items(), key=lambda kv: (kv[1][1], kv[1][0].lower(), kv[0])):
        writer.writerow([number(code), name, number(parent)])
    if level == "woreda":
        writer.writerow(["other", "Other", "other_woreda"])
    return buffer.getvalue()


def configure_location_widgets(workbook):
    """Keep submitted field paths/types, while using real cascading dropdowns."""
    sheet = workbook["survey"]
    columns = {cell.value: cell.column for cell in sheet[1] if cell.value}
    changed = False
    for row in range(2, sheet.max_row + 1):
        name = sheet.cell(row, columns["name"]).value
        level = str(name).removeprefix("hh_member_")
        updates = {}
        if level in ("zone", "woreda", "kebele"):
            filename = {"zone": "ZoneList.csv", "woreda": "WoredaList.csv", "kebele": "KebeleList.csv"}[level]
            updates = {"type": "select_one_from_file " + filename, "appearance": "minimal"}
        if name == "location" and sheet.cell(row, columns["type"]).value == "geopoint":
            updates = {"appearance": "placement-map"}
        for field, value in updates.items():
            cell = sheet.cell(row, columns[field])
            if cell.value != value:
                cell.value = value
                changed = True
    return changed


def _choices_sheet(workbook):
    sheet = workbook["choices"]
    header = [str(cell.value).strip() if cell.value is not None else "" for cell in sheet[1]]
    return sheet, header


def current_choice_rows(workbook) -> tuple[list[dict], dict[int, tuple[str, str]]]:
    sheet, header = _choices_sheet(workbook)
    col = {name: header.index(name) for name in ("list_name", "name", "region", "zone", *LABELS)}
    rows, translations = [], {}
    for values in sheet.iter_rows(min_row=2, values_only=True):
        if not values or values[col["list_name"]] not in LOCATION_LISTS:
            continue
        row = {"list_name": values[col["list_name"]], "name": values[col["name"]],
               "labels": tuple(values[col[label]] for label in LABELS)}
        if values[col["region"]] is not None:
            row["region"] = values[col["region"]]
        if values[col["zone"]] is not None:
            row["zone"] = values[col["zone"]]
        rows.append(row)
        if row["list_name"] == "choices_region":
            translations[row["name"]] = (row["labels"][1], row["labels"][2])
    return rows, translations


def write_choice_rows(workbook, rows: list[dict]) -> None:
    """Replace the location lists, which sit together in the sheet, in place."""
    sheet, header = _choices_sheet(workbook)
    col = {name: header.index(name) + 1 for name in ("list_name", "name", "region", "zone", *LABELS)}
    first = last = None
    for index, cell in enumerate(sheet["A"][1:], start=2):
        if cell.value in LOCATION_LISTS:
            first = first or index
            last = index
    sheet.delete_rows(first, last - first + 1)
    sheet.insert_rows(first, len(rows))
    for offset, row in enumerate(rows):
        number_row = first + offset
        sheet.cell(number_row, col["list_name"], row["list_name"])
        sheet.cell(number_row, col["name"], row["name"])
        for label, value in zip(LABELS, row["labels"]):
            sheet.cell(number_row, col[label], value)
        if "region" in row:
            sheet.cell(number_row, col["region"], row["region"])
        if "zone" in row:
            sheet.cell(number_row, col["zone"], row["zone"])


def main(argv: list[str]) -> int:
    import openpyxl

    levels = load_hierarchy()
    workbook = openpyxl.load_workbook(FORM)
    current, translations = current_choice_rows(workbook)
    wanted = choice_rows(levels, translations)
    media = {KEBELES: kebele_csv(levels), ZONES: parent_csv(levels, "zone"), WOREDAS: parent_csv(levels, "woreda")}
    widgets_changed = configure_location_widgets(workbook)
    stale = []
    if current != wanted:
        stale.append(f"{FORM.name} ({', '.join(LOCATION_LISTS)})")
    for path, content in media.items():
        if not path.exists() or path.read_bytes().decode("utf-8") != content:
            stale.append(path.name)
    if widgets_changed:
        stale.append("location widgets")
    if "--check" in argv:
        if stale:
            print(f"stale, rerun odk/build_location_media.py: {stale}", file=sys.stderr)
            return 1
        print("location lists match the shared hierarchy")
        return 0
    if current != wanted:
        write_choice_rows(workbook, wanted)
    if current != wanted or widgets_changed:
        workbook.save(FORM)
    for path, content in media.items():
        path.write_bytes(content.encode("utf-8"))
    print("updated: " + (", ".join(stale) if stale else "nothing, already current"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
