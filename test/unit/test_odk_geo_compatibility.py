"""Offline compatibility checks using the checked-in COSS hierarchy, never a DB."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/check_odk_geo_compatibility.py"
spec = importlib.util.spec_from_file_location("geo_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.fixture(scope="module")
def canonical():
    levels, values = audit.canonical_catalog()
    return {"levels": list(levels.values()), "values": list(values.values())}


@pytest.fixture
def catalog(canonical):
    return copy.deepcopy(canonical)


def reference(identity, count=1, table="fr_farmer_location"):
    return {"table": table, "geo_lowest_level_value_id": identity, "count": count}


def write_json(path, data):
    assert path.parent.is_dir()  # Verify the parent before generating any file.
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def run_cli(tmp_path, capsys, catalog, references=None, supplied=True):
    args = ["--catalog", str(write_json(tmp_path / "catalog.json", catalog))]
    if supplied:
        args += ["--references", str(write_json(tmp_path / "references.json", references))]
    code = audit.main(args)
    return code, json.loads(capsys.readouterr().out)


def test_real_cli_exact_catalog_and_references_are_read_only(tmp_path, canonical):
    catalog_path = write_json(tmp_path / "catalog.json", canonical)
    references_path = write_json(tmp_path / "references.json", [
        reference("kebele-ET010103201001", 7), reference("woreda-ET0420112", 3),
        reference("region-ET01", 2, "intake_location"),
    ])
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = subprocess.run([sys.executable, str(SCRIPT), "--catalog", str(catalog_path),
                             "--references", str(references_path)], cwd=tmp_path,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["compatible"] is True
    assert report["catalog"]["counts_by_level"] == report["catalog"]["expected_coss_counts"] == {
        "region": 14, "zone": 125, "woreda": 1379, "kebele": 19535,
    }
    assert report["references"]["exact_coss_ids"] == {"groups": 3, "records": 12}
    assert report["references"]["tables"] == 2
    assert "geo_lowest_level_value_id" not in result.stdout
    assert "ET010103201001" not in result.stdout
    assert "fr_farmer_location" not in result.stdout
    assert not result.stderr
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_empty_references_are_known_but_omitted_references_are_unknown(tmp_path, capsys, canonical):
    code, report = run_cli(tmp_path, capsys, canonical, [])
    assert code == 0 and report["references"]["coverage"] == "known"
    code, report = run_cli(tmp_path, capsys, canonical, supplied=False)
    assert code == 1
    assert report["catalog"]["compatible"] is True
    assert report["references"]["coverage"] == "unknown"
    assert report["references"]["already_exact"] is False


def test_country_root_legacy_snapshot_is_incompatible(tmp_path, capsys):
    names = ("country", "region", "zone", "woreda")
    ids = ("ET", "ET01", "ET0101", "ET010103")
    legacy = {"levels": [], "values": []}
    for i, (name, identity) in enumerate(zip(names, ids)):
        legacy["levels"].append({"level_id": name, "level_mnemonic": name,
                                 "parent_level_id": names[i - 1] if i else None})
        legacy["values"].append({"level_value_id": identity, "level_id": name,
                                 "parent_level_value_id": ids[i - 1] if i else None,
                                 "level_value_mnemonic": name.title()})
    code, report = run_cli(tmp_path, capsys, legacy, [reference("ET010103", 4)])
    assert code == 1
    assert report["catalog"]["level_shape_compatible"] is False
    assert report["catalog"]["counts_by_level"]["country"] == 1
    assert report["catalog"]["counts_by_level"]["kebele"] == 0
    assert report["references"]["legacy_et_pcode_candidates"] == {"groups": 1, "records": 4}


def test_missing_kebele_level_and_values(catalog):
    catalog["levels"] = [r for r in catalog["levels"] if r["level_mnemonic"] != "kebele"]
    catalog["values"] = [r for r in catalog["values"] if r["level_id"] != "level-kebele"]
    report = audit.audit(catalog, [])
    assert not report["compatible"]
    assert not report["catalog"]["level_shape_compatible"]
    assert report["catalog"]["values"]["missing_ids"] == 19535


def test_candidates_preserve_zeros_and_exceptional_woreda_without_guessing(tmp_path, capsys, canonical):
    refs = [reference("ET01", 2), reference("ET010103", 3), reference("ET0420112", 5),
            reference("ET010103201001", 7), reference("woreda-ET0420112", 11),
            reference("kamuntu", 13), reference("ET420112", 17), reference("ET1", 19),
            reference("ET999999", 23), reference("Sululta", 29)]
    code, report = run_cli(tmp_path, capsys, canonical, refs)
    assert code == 1 and report["catalog"]["compatible"] is True
    summary = report["references"]
    assert summary["exact_coss_ids"] == {"groups": 1, "records": 11}
    assert summary["legacy_et_pcode_candidates"] == {"groups": 4, "records": 17}
    assert summary["unmappable"] == {"groups": 5, "records": 101}
    assert summary["records"] == 129
    rendered = json.dumps(report)
    assert all(row["geo_lowest_level_value_id"] not in rendered for row in refs)


def test_candidates_alone_never_pass(tmp_path, capsys, canonical):
    code, report = run_cli(tmp_path, capsys, canonical, [reference("ET0420112")])
    assert code == 1 and not report["references"]["already_exact"]


def test_labels_and_valid_but_wrong_parents_are_incompatible(catalog):
    zones = [r for r in catalog["values"] if r["level_id"] == "level-zone"]
    first = zones[0]
    first["level_value_mnemonic"] += " changed"
    first["parent_level_value_id"] = next(r["parent_level_value_id"] for r in zones
                                          if r["parent_level_value_id"] != first["parent_level_value_id"])
    report = audit.audit(catalog, [])
    assert not report["compatible"]
    assert report["catalog"]["level_shape_compatible"]
    assert report["catalog"]["values"]["level_value_mnemonic_mismatches"] == 1
    assert report["catalog"]["values"]["parent_level_value_id_mismatches"] == 1


def test_equal_counts_do_not_hide_wrong_ids(catalog):
    kebele = next(r for r in catalog["values"] if r["level_id"] == "level-kebele")
    kebele["level_value_id"] = "kebele-not-a-coss-id"
    report = audit.audit(catalog, [])
    assert not report["compatible"]
    assert report["catalog"]["counts_by_level"] == report["catalog"]["expected_coss_counts"]
    assert report["catalog"]["values"]["missing_ids"] == 1
    assert report["catalog"]["values"]["extra_ids"] == 1


def test_level_ids_must_match_even_with_the_right_shape(catalog):
    for level in catalog["levels"]:
        if level["level_id"] == "level-kebele":
            level["level_id"] = "legacy-kebele"
    for row in catalog["values"]:
        if row["level_id"] == "level-kebele":
            row["level_id"] = "legacy-kebele"
    report = audit.audit(catalog, [])
    assert report["catalog"]["level_shape_compatible"]
    assert not report["compatible"]
    assert report["catalog"]["levels"]["missing_ids"] == 1
    assert report["catalog"]["levels"]["extra_ids"] == 1
    assert report["catalog"]["values"]["level_id_mismatches"] == 19535


@pytest.mark.parametrize("problem", [
    "duplicate_level", "duplicate_value", "duplicate_mnemonic", "missing_label", "missing_parent",
    "null_label", "numeric_id", "unknown_level", "dangling_value", "wrong_parent_level",
    "dangling_level", "cyclic_levels", "two_roots", "empty_levels", "not_a_list", "not_an_object",
])
def test_malformed_catalog_fails_closed(tmp_path, capsys, canonical, problem):
    # One complete ancestor chain is enough to exercise validation independently
    # of catalog completeness, which is a compatibility result, not a parse error.
    by_id = {row["level_value_id"]: row for row in canonical["values"]}
    row = next(r for r in canonical["values"] if r["level_id"] == "level-kebele")
    chain = []
    while row:
        chain.append(copy.deepcopy(row))
        row = by_id.get(row["parent_level_value_id"])
    data = {"levels": copy.deepcopy(canonical["levels"]), "values": chain}
    if problem == "duplicate_level":
        data["levels"].append(data["levels"][0])
    elif problem == "duplicate_value":
        data["values"].append(data["values"][0])
    elif problem == "duplicate_mnemonic":
        data["levels"][1]["level_mnemonic"] = data["levels"][0]["level_mnemonic"]
    elif problem == "missing_label":
        del chain[0]["level_value_mnemonic"]
    elif problem == "missing_parent":
        del chain[0]["parent_level_value_id"]
    elif problem == "null_label":
        chain[0]["level_value_mnemonic"] = None
    elif problem == "numeric_id":
        chain[0]["level_value_id"] = 123
    elif problem == "unknown_level":
        chain[0]["level_id"] = "not-a-level"
    elif problem == "dangling_value":
        chain[0]["parent_level_value_id"] = "not-a-parent"
    elif problem == "wrong_parent_level":
        chain[0]["parent_level_value_id"] = chain[-1]["level_value_id"]
    elif problem == "dangling_level":
        data["levels"][1]["parent_level_id"] = "not-a-level"
    elif problem == "cyclic_levels":
        data["levels"][1]["parent_level_id"] = "level-woreda"
    elif problem == "two_roots":
        data["levels"][1]["parent_level_id"] = None
    elif problem == "empty_levels":
        data["levels"] = []
    elif problem == "not_a_list":
        data["values"] = {}
    elif problem == "not_an_object":
        data = []
    code, report = run_cli(tmp_path, capsys, data, [])
    assert code == 2 and report["compatible"] is False
    assert "error" in report


@pytest.mark.parametrize("count", [True, False, -1, 0, 1.0, "1", None, 2**63])
def test_invalid_reference_counts(tmp_path, capsys, canonical, count):
    code, report = run_cli(tmp_path, capsys, canonical, [reference("kamuntu", count)])
    assert code == 2 and report["compatible"] is False
    assert "kamuntu" not in json.dumps(report)


@pytest.mark.parametrize("refs", [
    None, {}, [None], [reference(123)], [reference("")],
    [reference("region-ET01"), reference("region-ET01")],
    [{**reference("kamuntu"), "farmer_name": "must-not-be-echoed"}],
])
def test_invalid_or_nonaggregate_references(tmp_path, capsys, canonical, refs):
    code, report = run_cli(tmp_path, capsys, canonical, refs)
    assert code == 2
    assert "must-not-be-echoed" not in json.dumps(report)


def test_same_reference_id_in_different_tables_is_not_a_duplicate(canonical):
    report = audit.audit(canonical, [reference("region-ET01", 2, "first_table"),
                                     reference("region-ET01", 3, "second_table")])
    assert report["compatible"]
    assert report["references"]["exact_coss_ids"] == {"groups": 2, "records": 5}


@pytest.mark.parametrize("raw", [
    b'{"levels": [], "levels": [], "values": []}',
    b'{"levels": [], "values": [], "extra": NaN}',
    b'{"private-reference-id":', b'\xff',
])
def test_bad_json_never_echoes_input(tmp_path, capsys, raw):
    path = tmp_path / "catalog.json"
    assert path.parent.is_dir()
    path.write_bytes(raw)
    assert audit.main(["--catalog", str(path)]) == 2
    output = capsys.readouterr().out
    assert json.loads(output)["compatible"] is False
    assert "private-reference-id" not in output


def test_snapshot_size_and_row_limits(tmp_path, capsys, monkeypatch):
    path = write_json(tmp_path / "catalog.json", {"levels": [], "values": []})
    monkeypatch.setattr(audit, "MAX_BYTES", 8)
    assert audit.main(["--catalog", str(path)]) == 2
    assert json.loads(capsys.readouterr().out)["compatible"] is False
    monkeypatch.setattr(audit, "MAX_ROWS", 0)
    with pytest.raises(ValueError, match="Invalid references list"):
        audit.reference_summary([reference("ET01")], {})


def test_missing_snapshot_is_a_json_error(tmp_path, capsys):
    assert audit.main(["--catalog", str(tmp_path / "absent.json")]) == 2
    assert json.loads(capsys.readouterr().out)["compatible"] is False
