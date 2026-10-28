"""The farmer ODK form's choice lists are Master Data's (odk/tools/build_mds_form.py)."""
import csv
import importlib.util
import json
from pathlib import Path

import openpyxl
import pytest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("build_mds_form", REPO / "odk/tools/build_mds_form.py")
build_mds_form = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_mds_form)

LABELS = build_mds_form.LABELS


def mds_list(attribute_id, codes):
    return {"attribute_id": attribute_id, "attribute_code": attribute_id, "attribute_display": attribute_id,
            "is_hierarchical": False, "values": [
                {"value_id": f"{attribute_id}_{c}", "value_code": c, "value_display": c.replace("_", " ").title(),
                 "sort_order": i + 1, "display_i18n": {}} for i, c in enumerate(codes)]}


@pytest.fixture
def pack(tmp_path):
    """A pack with every list the form needs, two of each geography level."""
    root = tmp_path / "ETH-TEST"
    (root / "codelists").mkdir(parents=True)
    (root / "domains/agriculture").mkdir(parents=True)
    lists = {
        "GENDER": ["FEMALE", "MALE", "OTHER"], "LANGUAGE": ["AMHARIC", "AFAAN_OROMO", "GEDEO"],
        "FARMING_TYPE": ["CROP", "LIVESTOCK", "MIXED", "AQUACULTURE"], "MARITAL_STATUS": ["SINGLE", "MARRIED"],
        "EDUCATION_LEVEL": ["ILLITERATE", "CAN_READ_AND_WRITE", "TERTIARY"],
        "SOURCE_OF_INCOME": ["SOI_CROP_PRODUCTION", "SOI_LIVESTOCK_PRODUCTION", "SOI_OTHERS"],
        "CROP_COMMODITY": ["CROP_TEFF", "CROP_MAIZE", "CROP_BREAD_WHEAT", "CROP_MALT_BARLEY"],
        "FARMER_CLUSTER_ROLE": ["LEAD", "MEMBER"], "LAND_OWNERSHIP_TYPE": ["OWNER", "TENANT", "HYBRID"],
        "CROP_SEASON": ["SEASON_MEHER", "SEASON_BELG"], "WATER_SOURCE": ["WS_RAINFED", "WS_WELL_GROUND", "WS_SURFACE_WATER"],
        "LIVESTOCK_TYPE": ["LSTK_CATTLE", "LSTK_GOAT"], "FARM_MACHINERY": ["MACH_TRACTOR", "MACH_SPRAYER"],
        "FINANCE_ACCESS_TYPE": ["LOAN", "SAVING"], "IDENTITY_DOCUMENT_TYPE": ["FAYDA", "PASSPORT"],
        "RELATIONSHIP_TO_HEAD": ["SELF", "SPOUSE", "CHILD", "OTHER_RELATIVE"],
    }
    for attribute_id, codes in lists.items():
        folder = "domains/agriculture" if attribute_id in ("CROP_COMMODITY", "CROP_SEASON", "FARM_MACHINERY", "FINANCE_ACCESS_TYPE") else "codelists"
        (root / folder / f"{attribute_id.lower()}.json").write_text(json.dumps(mds_list(attribute_id, codes)), encoding="utf-8")
    (root / "levels.json").write_text(json.dumps([
        {"level_id": "l0", "level_mnemonic": "country", "parent_level_id": None},
        {"level_id": "l1", "level_mnemonic": "region", "parent_level_id": "l0"},
        {"level_id": "l2", "level_mnemonic": "zone", "parent_level_id": "l1"},
        {"level_id": "l3", "level_mnemonic": "woreda", "parent_level_id": "l2"},
        {"level_id": "l4", "level_mnemonic": "kebele", "parent_level_id": "l3"}]), encoding="utf-8")
    units = [{"level_value_id": "ET", "level_id": "l0", "display_name": "Ethiopia", "parent_level_value_id": None}]
    for r in ("01", "02"):
        units.append({"level_value_id": f"ET{r}", "level_id": "l1", "display_name": f"Region {r}", "parent_level_value_id": "ET"})
        for z in ("01", "02"):
            units.append({"level_value_id": f"ET{r}{z}", "level_id": "l2", "display_name": f"Zone {r}{z}", "parent_level_value_id": f"ET{r}"})
            units.append({"level_value_id": f"ET{r}{z}01", "level_id": "l3", "display_name": f"Woreda {r}{z}01", "parent_level_value_id": f"ET{r}{z}"})
            units.append({"level_value_id": f"ET{r}{z}0101", "level_id": "l4", "display_name": f"Kebele {r}{z}0101", "parent_level_value_id": f"ET{r}{z}01"})
    (root / "values.json").write_text(json.dumps(units), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps({"version": "test"}), encoding="utf-8")
    return root


def test_every_master_data_list_replaces_its_choice_list(pack, tmp_path):
    out = tmp_path / "form.xlsx"
    media = tmp_path / "media"
    report = build_mds_form.build(build_mds_form.SOURCE, pack, out, media, "test-version")
    book = openpyxl.load_workbook(out, read_only=True)
    rows = list(book["choices"].iter_rows(values_only=True))
    header = list(rows[0])
    by_list = {}
    for row in rows[1:]:
        if row[0]:
            by_list.setdefault(row[0], []).append(dict(zip(header, row)))
    lists = build_mds_form.read_lists(pack)
    for name, (attribute_id, _, left_out) in build_mds_form.MDS_LISTS.items():
        expected = [v["value_code"] for v in lists[attribute_id]["values"] if v["value_code"] not in left_out]
        assert [r["name"] for r in by_list[name]] == expected, name
        for r in by_list[name]:
            assert all(r.get(label) for label in LABELS), (name, r["name"])
    # A code the old form knew keeps its translations; the member's relationship never offers SELF.
    gender = {r["name"]: r for r in by_list["choices_gender"]}
    assert gender["MALE"]["label::Amharic (am)"] != gender["OTHER"]["label::Amharic (am)"]
    assert "SELF" not in [r["name"] for r in by_list["choices_household_relationship"]]
    # Lists that are not Master Data stay as they were: yes/no, consent, unions.
    assert [r["name"] for r in by_list["choices_phone_number"]] == ["yes", "no"]
    assert len(by_list["choices_name_union"]) == 164
    assert "choices_region" not in by_list
    assert report["lists"]["choices_machinery"]["master_data_list"] == "FARM_MACHINERY"
    assert book["settings"].cell(2, 3).value == "test-version"
    # The geography is the pack's hierarchy, one external list per level, P-codes as name and code.
    for level, count in (("region", 2), ("zone", 4), ("woreda", 4), ("kebele", 4)):
        with (media / f"{level}.csv").open(encoding="utf-8", newline="") as handle:
            units = list(csv.DictReader(handle))
        assert len(units) == count == report["units"][level]
        assert all(u["name"] == u["code"] and u["label"] for u in units)
        if level != "region":
            assert all(u["parent"] and u["code"].startswith(u["parent"]) for u in units)
    survey = list(book["survey"].iter_rows(values_only=True))
    types = {row[1]: row[0] for row in survey[1:] if row[1]}
    for level in build_mds_form.LEVELS:
        assert types[level] == f"select_one_from_file {level}.csv"
        assert types["hh_member_" + level] == f"select_one_from_file {level}.csv"


def test_choice_rows_report_old_choices_master_data_does_not_have():
    old = [{"name": "tractor", "label::English (en)": "Tractor", "label::Amharic (am)": "ትራክተር"},
           {"name": "rice_polisher", "label::English (en)": "Rice polisher"}]
    rows, info = build_mds_form.choice_rows(old, mds_list("FARM_MACHINERY", ["MACH_TRACTOR", "MACH_SPRAYER"]),
                                            build_mds_form.MDS_LISTS["choices_machinery"][1], set())
    assert [r["name"] for r in rows] == ["MACH_TRACTOR", "MACH_SPRAYER"]
    assert rows[0]["label::Amharic (am)"] == "ትራክተር" and rows[1]["label::Amharic (am)"] == "Mach Sprayer"
    assert info == {"codes": 2, "translated": 1, "dropped_choices": ["rice_polisher"]}


def test_geography_comes_from_the_environments_master_data(pack, tmp_path):
    """An environment migrated from an older catalogue keeps its own unit ids;
    the form's location lists carry those, not the pack's."""
    geo = tmp_path / "env-geo"
    geo.mkdir()
    (geo / "levels.json").write_text(json.dumps([
        {"level_id": "level-region", "level_mnemonic": "region", "parent_level_id": None},
        {"level_id": "level-zone", "level_mnemonic": "zone", "parent_level_id": "level-region"},
        {"level_id": "level-woreda", "level_mnemonic": "woreda", "parent_level_id": "level-zone"},
        {"level_id": "level-kebele", "level_mnemonic": "kebele", "parent_level_id": "level-woreda"}]), encoding="utf-8")
    (geo / "values.json").write_text(json.dumps([
        {"level_value_id": "region-ET01", "level_id": "level-region", "display_name": "Tigray", "parent_level_value_id": None},
        {"level_value_id": "zone-ET0101", "level_id": "level-zone", "display_name": "North Western", "parent_level_value_id": "region-ET01"},
        {"level_value_id": "woreda-ET010101", "level_id": "level-woreda", "display_name": "Tahtay Adiyabo", "parent_level_value_id": "zone-ET0101"},
        {"level_value_id": "kebele-ET010101101001", "level_id": "level-kebele", "display_name": "Kebele 1", "parent_level_value_id": "woreda-ET010101"}]), encoding="utf-8")
    media = tmp_path / "media"
    report = build_mds_form.build(build_mds_form.SOURCE, pack, tmp_path / "form.xlsx", media, "v", geography=geo)
    assert report["units"] == {"region": 1, "zone": 1, "woreda": 1, "kebele": 1}
    with (media / "kebele.csv").open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == [{"name": "kebele-ET010101101001", "label": "Kebele 1",
                                                 "code": "kebele-ET010101101001", "parent": "woreda-ET010101"}]
    with (media / "region.csv").open(encoding="utf-8", newline="") as handle:
        assert [r["name"] for r in csv.DictReader(handle)] == ["region-ET01"]
