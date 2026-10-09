"""The farmer form's location lists are the shared location hierarchy.

docs/odk/build_location_media.py generates the form's region / zone / woreda
choice lists and media/KebeleList.csv from
docker/db-seed/seed-data/geo/geo_level_values.json, the hierarchy Master Data
is seeded with. If they drift, an agent can pick a kebele Master Data does not
know (the ingest then has no location), or cannot pick one it does.
"""

import csv
import importlib.util
import pathlib

import pytest

openpyxl = pytest.importorskip("openpyxl")

REPO = pathlib.Path(__file__).resolve().parent.parent
ODK = REPO / "docs" / "odk"

spec = importlib.util.spec_from_file_location("build_location_media", ODK / "build_location_media.py")
build_location_media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_location_media)

LEVELS = build_location_media.load_hierarchy()


@pytest.fixture(scope="module")
def workbook():
    return openpyxl.load_workbook(build_location_media.FORM, read_only=True)


def test_choice_lists_and_kebele_list_are_what_the_generator_builds(workbook):
    current, translations = build_location_media.current_choice_rows(workbook)
    assert current == build_location_media.choice_rows(LEVELS, translations), (
        "location choice lists are stale: run python docs/odk/build_location_media.py"
    )
    assert build_location_media.KEBELES.read_bytes().decode("utf-8") == build_location_media.kebele_csv(LEVELS), (
        "KebeleList.csv is stale: run python docs/odk/build_location_media.py"
    )


def test_every_kebele_pads_to_a_master_data_id():
    """farmer_transform.j2 sends kebele-ET + the code padded to 12 digits."""
    master_data = {f"kebele-ET{code}" for code in LEVELS["kebele"]}
    rows = [row for row in csv.DictReader(build_location_media.KEBELES.open(encoding="utf-8")) if row["name"] != "other"]
    sent = {f"kebele-ET{int(row['name']):012d}" for row in rows}
    assert len(rows) == len(LEVELS["kebele"]) == 19535
    assert sent == master_data


def test_regions_carry_their_translations(workbook):
    current, _ = build_location_media.current_choice_rows(workbook)
    regions = [row for row in current if row["list_name"] == "choices_region"]
    assert len(regions) == 14
    for row in regions:
        english, amharic, oromo = row["labels"]
        assert amharic and oromo and amharic != english, row


def test_cooperatives_and_unions_hang_under_a_region_the_form_offers(workbook):
    current, _ = build_location_media.current_choice_rows(workbook)
    regions = {str(row["name"]) for row in current if row["list_name"] == "choices_region"}
    coops = {row["region"] for row in csv.DictReader((ODK / "media" / "PrimaryCoopList.csv").open(encoding="utf-8"))}
    sheet = workbook["choices"]
    header = [str(cell).strip() if cell else "" for cell in next(sheet.iter_rows(values_only=True))]
    unions = {
        str(row[header.index("region")])
        for row in sheet.iter_rows(min_row=2, values_only=True)
        if row and row[0] == "choices_name_union"
    }
    assert coops - {"other_primary_coop"} <= regions
    assert unions - {"other_union"} <= regions
