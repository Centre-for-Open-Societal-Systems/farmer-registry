"""The farmer form's location lists are the shared location hierarchy.

odk/build_location_media.py generates the form's region / zone / woreda
choice lists and external CSV media from
odk/legacy-geo/ethiopia_geo_seed.sql.gz, the hierarchy Master Data
is seeded with. If they drift, an agent can pick a kebele Master Data does not
know (the ingest then has no location), or cannot pick one it does.
"""

import csv
import importlib.util
import pathlib
import json

from jinja2 import Environment

import pytest

openpyxl = pytest.importorskip("openpyxl")

REPO = pathlib.Path(__file__).resolve().parents[2]
ODK = REPO / "odk"

spec = importlib.util.spec_from_file_location("build_location_media", ODK / "build_location_media.py")
build_location_media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_location_media)

LEVELS = build_location_media.load_hierarchy()


@pytest.fixture(scope="module")
def workbook():
    return openpyxl.load_workbook(build_location_media.FORM, read_only=True)


def test_choice_lists_and_kebele_list_are_what_the_generator_builds(workbook):
    current, translations = build_location_media.current_choice_rows(workbook)
    assert {row["list_name"] for row in current} == {"choices_region"}
    assert current == build_location_media.choice_rows(LEVELS, translations), (
        "location choice lists are stale: run python odk/build_location_media.py"
    )
    assert build_location_media.KEBELES.read_bytes().decode("utf-8") == build_location_media.kebele_csv(LEVELS), (
        "KebeleList.csv is stale: run python odk/build_location_media.py"
    )


def test_every_kebele_pads_to_a_master_data_id():
    """farmer_transform.j2 sends kebele-ET + the code padded to 12 digits."""
    master_data = {f"kebele-ET{code}" for code in LEVELS["kebele"]}
    rows = [row for row in csv.DictReader(build_location_media.KEBELES.open(encoding="utf-8")) if row["name"] != "other"]
    sent = {f"kebele-ET{int(row['name']):012d}" for row in rows}
    assert len(rows) == len(LEVELS["kebele"]) == 19535
    assert sent == master_data


def test_every_woreda_round_trips_through_the_actual_transform():
    template = Environment().from_string((ODK / 'templates/farmer_transform.j2').read_text(encoding='utf-8'))
    for code in LEVELS['woreda']:
        rendered = json.loads(template.render(data={'basic_info': {'locale_info': {
            'woreda': str(int(code)), 'kebele': 'other'}}}))
        assert rendered['fr_farmer_location'][0]['geo_lowest_level_value_id'] == 'woreda-ET' + code


def test_kebele_csv_filter_columns_and_unique_choice_names():
    with build_location_media.KEBELES.open(encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ['name', 'label', 'woreda']
        rows = list(reader)
    assert len({r['name'] for r in rows}) == len(rows)
    for row in rows:
        if row['name'] == 'other':
            continue
        code = f"{int(row['name']):012d}"
        name, woreda = LEVELS['kebele'][code]
        assert row['label'] == name
        assert row['woreda'] == str(int(woreda))


@pytest.mark.parametrize('level,path', [('zone', build_location_media.ZONES), ('woreda', build_location_media.WOREDAS)])
def test_external_parent_lists_preserve_every_canonical_name_and_parent(level, path):
    assert path.read_text(encoding='utf-8') == build_location_media.parent_csv(LEVELS, level)
    with path.open(encoding='utf-8') as source:
        rows = [r for r in csv.DictReader(source) if r['name'] != 'other']
    assert len(rows) == len(LEVELS[level])
    parent_column = 'region' if level == 'zone' else 'zone'
    for row in rows:
        code = next(code for code in LEVELS[level] if int(code) == int(row['name']))
        name, parent = LEVELS[level][code]
        assert row['label'] == name and row[parent_column] == str(int(parent))


def test_primary_and_household_locations_use_dropdowns_and_manual_map(workbook):
    sheet = workbook['survey']
    headers = list(next(sheet.iter_rows(values_only=True)))
    rows = {r[headers.index('name')]: dict(zip(headers, r)) for r in sheet.iter_rows(min_row=2, values_only=True) if r[headers.index('name')]}
    for prefix in ('', 'hh_member_'):
        for level, filename in [('zone', 'ZoneList.csv'), ('woreda', 'WoredaList.csv'), ('kebele', 'KebeleList.csv')]:
            row = rows[prefix + level]
            assert row['type'] == 'select_one_from_file ' + filename
            assert row['appearance'] == 'minimal'
    assert rows['location']['type'] == 'geopoint'
    assert rows['location']['appearance'] == 'placement-map'


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
