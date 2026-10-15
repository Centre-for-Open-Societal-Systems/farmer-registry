"""Offline migration safety tests. Never connect to a DB or read backup contents."""

import copy
import csv
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
from collections import Counter

import pytest

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("shared_geo", REPO / "scripts/migrate-shared-odk-geography.py")
geo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geo)


@pytest.fixture(scope="module")
def canonical():
    return geo.canonical()


@pytest.fixture(scope="module")
def source_catalog():
    # Independent CSV-based oracle for the checked-in seed's SQL quoting convention.
    source = REPO / "local/upstream/assets/geo/ethiopia_geo_seed.sql.gz"
    catalogs = {table: {} for table in geo.TABLES}
    for line in gzip.decompress(source.read_bytes()).decode("utf-8").splitlines():
        if not line.startswith("INSERT INTO public.g2p_geo_"):
            continue
        head, tail = line.split(") VALUES (", 1)
        table, columns = head.removeprefix("INSERT INTO public.").split(" (", 1)
        text = tail.rsplit(") ON CONFLICT (", 1)[0]
        literals = next(csv.reader([text], quotechar="'", skipinitialspace=True, strict=True))
        row = dict(zip((c.strip() for c in columns.split(',')),
                       (None if v == "NULL" else v for v in literals), strict=True))
        key = "level_id" if table == geo.TABLES[0] else "level_value_id"
        catalogs[table][row[key]] = row
    return tuple(catalogs[t] for t in geo.TABLES)


def seed_text(catalogs):
    lines = []
    for table, catalog in zip(geo.TABLES, catalogs):
        key = "level_id" if table == geo.TABLES[0] else "level_value_id"
        for row in catalog.values():
            values = ", ".join("NULL" if v is None else "'" + v.replace("'", "''") + "'" for v in row.values())
            lines.append(f"INSERT INTO public.{table} ({', '.join(row)}) VALUES ({values}) ON CONFLICT ({key}) DO NOTHING;")
    return "\n".join(lines)


@pytest.fixture
def legacy(canonical):
    levels, values, _ = canonical
    names = ("country", "region", "zone", "woreda", "kebele")
    old_levels = {f"l{i}": dict(level_id=f"l{i}", level_mnemonic=n,
        parent_level_id=f"l{i-1}" if i else None) for i, n in enumerate(names)}
    old_values = {"ET": dict(level_value_id="ET", level_id="l0", level_value_mnemonic="Ethiopia",
                             parent_level_value_id=None)}
    for v in geo.chain("kebele-ET010103201001", values):
        key = v["level_value_id"].split("-", 1)[1]
        parent = v["parent_level_value_id"]
        old_values[key] = dict(level_value_id=key, level_id="l" + str(names.index(levels[v["level_id"]]["level_mnemonic"])),
            level_value_mnemonic=v["level_value_mnemonic"],
            parent_level_value_id=parent.split("-", 1)[1] if parent else "ET")
    return old_levels, old_values


def select(lowest, raw, legacy, canonical):
    old_levels, old_values = legacy
    levels, values, _ = canonical
    aliases = geo.mapping(old_levels, old_values, levels, values)
    return geo.selection(lowest, raw, aliases, old_levels, old_values, levels, values)


def test_canonical_source_counts_labels_metadata_and_exception(canonical):
    levels, values, digest = canonical
    assert len(digest) == 64
    assert {n: sum(v["level_id"] == "level-" + n for v in values.values()) for n in geo.PARENTS} == {
        "region": 14, "zone": 125, "woreda": 1379, "kebele": 19535}
    assert values["woreda-ET0420112"]["level_id"] == "level-woreda"
    assert levels["level-region"]["parent_level_id"] is None
    siblings = set()
    for v in values.values():
        identity = (v["level_id"], v["parent_level_value_id"], v["level_value_mnemonic"])
        assert identity not in siblings
        siblings.add(identity)
    assert any(" (ET" in v["level_value_mnemonic"] for v in values.values())


def test_canonical_preserves_every_source_field_except_selectable_labels(canonical, source_catalog):
    levels, values, _ = canonical
    source_levels, source_values = source_catalog
    assert levels == source_levels
    assert values.keys() == source_values.keys()
    duplicates = Counter((r["level_id"], r["parent_level_value_id"], r["level_value_mnemonic"])
                         for r in source_values.values())
    changed = 0
    for key, row in source_values.items():
        expected = dict(row)
        label = row["level_value_mnemonic"].strip()
        if duplicates[(row["level_id"], row["parent_level_value_id"], row["level_value_mnemonic"])] > 1:
            label += " (" + key.split('-', 1)[1] + ")"
            changed += 1
            assert values[key]["display_name"] == row["display_name"] != label
        expected["level_value_mnemonic"] = label
        assert values[key] == expected
    assert changed > 0


def test_nonnull_metadata_dates_and_future_columns_survive_canonical_loading(source_catalog, canonical, monkeypatch, tmp_path):
    levels, values = copy.deepcopy(source_catalog)
    target = next(k for k, v in canonical[1].items() if " (ET" in v["level_value_mnemonic"])
    for catalog in (levels, values):
        for row in catalog.values():
            row["source"] = "COSS's published catalogue, 2026"
    levels["level-region"].update(display_name="Region, O'Brien", display_name_i18n='{"am":"ክልል"}',
        version="2026.10", valid_from="2026-10-15", valid_to="2027-10-15")
    values[target].update(pcode=target.split('-', 1)[1], pcode_source="COSS's P-code source",
        display_name="Original display name", display_name_i18n='{"en":"Display, name","am":"ቀበሌ"}',
        boundary_uri="https://example.invalid/full", boundary_simplified_uri="https://example.invalid/simple",
        version="2026.10", valid_from="2026-10-15", valid_to="2027-10-15")
    seed = gzip.compress(seed_text((levels, values)).encode("utf-8"))
    source = REPO / "local/upstream/assets/geo/ethiopia_geo_seed.sql.gz"
    read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda path: seed if path == source else read_bytes(path))
    actual_levels, actual_values, digest = geo.canonical()
    assert actual_levels == levels
    expected = dict(values[target], level_value_mnemonic=canonical[1][target]["level_value_mnemonic"])
    assert actual_values[target] == expected
    assert all(actual_values[k]["source"] == v["source"] for k, v in values.items())
    assert digest == hashlib.sha256(seed).hexdigest()
    # read_catalog uses PostgreSQL row_to_json: DATEs arrive as JSON strings,
    # not native datetime/date objects requiring a custom journal encoder.
    current = json.loads(json.dumps((actual_levels, actual_values)))
    assert current[0]["level-region"]["valid_from"] == "2026-10-15"
    assert geo.catalog_matches(current, (actual_levels, actual_values))
    geo.persist(tmp_path / "recovery.json", {"catalogs": current}, initial=True)
    assert json.loads((tmp_path / "recovery.json").read_text(encoding="utf-8"))["catalogs"] == current


def test_seed_parser_preserves_strings_null_quotes_and_unknown_metadata():
    catalogs = ({"level-region": dict(level_id="level-region", level_mnemonic="region", parent_level_id=None,
        source="NULL", display_name="Region's, name", valid_from="2026-10-15", extra="now(); SELECT 1;")},
        {"region-ET01": dict(level_value_id="region-ET01", level_id="level-region", parent_level_value_id=None,
        level_value_mnemonic="Label", display_name_i18n='{"am":"ክልል","en":"Quoted \'label\'"}', pcode_source=None)})
    assert geo.seed_catalog(seed_text(catalogs)) == catalogs


@pytest.mark.parametrize("bad", [
    "VALUES (now())", "VALUES (DEFAULT)", "VALUES (42)", "VALUES ('id',)",
    "VALUES ('id'); COMMIT;", "VALUES ('id') ON CONFLICT (level_value_id) DO NOTHING;",
])
def test_seed_parser_rejects_expressions_and_malformed_rows(bad):
    prefix = "INSERT INTO public.g2p_geo_levels (level_id) "
    suffix = " ON CONFLICT (level_id) DO NOTHING;"
    with pytest.raises(geo.Refused):
        geo.seed_catalog(prefix + bad + suffix)


def test_seed_parser_rejects_duplicate_ids_columns_and_missing_catalogs():
    levels = "INSERT INTO public.g2p_geo_levels (level_id) VALUES ('level-region') ON CONFLICT (level_id) DO NOTHING;"
    values = "INSERT INTO public.g2p_geo_level_values (level_value_id) VALUES ('region-ET01') ON CONFLICT (level_value_id) DO NOTHING;"
    for text in (levels, values, "", levels + "\n" + levels + "\n" + values,
                 levels.replace("(level_id) VALUES ('level-region')", "(level_id,level_id) VALUES ('a','b')") + "\n" + values):
        with pytest.raises(geo.Refused):
            geo.seed_catalog(text)


def test_exact_codes_only_and_old_country_is_omitted(legacy, canonical):
    old_levels, old_values = legacy
    levels, values, _ = canonical
    # Optional pcode metadata and labels do NOT license alias/name-based matching.
    old_values["alias"] = dict(old_values["ET01"], level_value_id="alias", pcode="ET01")
    old_values["ET1"] = dict(old_values["ET01"], level_value_id="ET1")
    aliases = geo.mapping(old_levels, old_values, levels, values)
    assert aliases["ET01"] == "region-ET01"
    assert aliases["ET010103201001"] == "kebele-ET010103201001"
    assert aliases["woreda-ET0420112"] == "woreda-ET0420112"
    assert not {"ET", "alias", "ET1"} & aliases.keys()


@pytest.mark.parametrize("problem", ["cycle", "dangling", "wrong_level", "duplicate_name", "level_cycle", "bad_shape"])
def test_bad_catalogs_and_inconsistent_mapping_fail_closed(legacy, canonical, problem):
    old_levels, old_values = legacy
    levels, values, _ = canonical
    if problem == "cycle":
        old_values["ET01"]["parent_level_value_id"] = "ET010103"
    elif problem == "dangling":
        old_values["ET01"]["parent_level_value_id"] = "missing"
    elif problem == "wrong_level":
        old_values["ET010103"]["level_id"] = "l1"
    elif problem == "duplicate_name":
        old_levels["duplicate"] = dict(old_levels["l1"])
    elif problem == "level_cycle":
        old_levels["l0"]["parent_level_id"] = "l1"
    else:
        old_levels["l2"]["parent_level_id"] = "l0"
    with pytest.raises(geo.Refused):
        geo.mapping(old_levels, old_values, levels, values)


def test_changed_jurisdiction_excludes_alias_and_descendants_without_guessing(legacy, canonical):
    old_levels, old_values = legacy
    levels, values, _ = canonical
    old_values["ET02"] = dict(old_values["ET01"], level_value_id="ET02")
    old_values["ET0101"]["parent_level_value_id"] = "ET02"
    aliases = geo.mapping(old_levels, old_values, levels, values)
    assert aliases["ET01"] == "region-ET01"
    assert not {"ET0101", "ET010103", "ET010103201001"} & aliases.keys()
    assert geo.selection("ET010103", None, aliases, old_levels, old_values, levels, values) == ("unmapped", None)


@pytest.mark.parametrize("raw", [None, "null", "{}", " { } "])
def test_empty_selections_are_not_unmapped(raw, legacy, canonical):
    assert select(None, raw, legacy, canonical) == ("empty", None)


def test_mapped_hierarchy_preserves_extra_keys_and_is_idempotent(legacy, canonical):
    old_levels, old_values = legacy
    obj = geo.hierarchy("ET010103201001", old_levels, old_values)
    obj["source"] = {"private-extra": [1, 2]}
    obj["hierarchy"][-1]["annotation"] = "keep"
    original = copy.deepcopy(obj)
    category, (target, updated) = select(None, json.dumps(obj), legacy, canonical)
    assert category == "candidate" and target == "kebele-ET010103201001"
    assert obj == original
    assert updated["source"] == obj["source"]
    assert updated["hierarchy"][-1]["annotation"] == "keep"
    assert [r["level"] for r in updated["hierarchy"]] == list(geo.PARENTS)
    assert set(updated["hierarchy"][0]) == {"level", "level_id", "level_mnemonic", "level_value_id", "level_value_mnemonic"}
    assert select(target, json.dumps(updated), legacy, canonical)[0] == "canonical"


def test_legacy_three_field_hierarchy_is_upgraded_without_losing_extras(legacy, canonical):
    obj = geo.hierarchy("ET010103", *legacy)
    obj.pop("lowest_level_value_id")
    for row in obj["hierarchy"]:
        row.pop("level")
        row.pop("level_id")
    obj["source"] = "retained"
    category, (target, updated) = select("ET010103", json.dumps(obj), legacy, canonical)
    assert category == "candidate" and target == "woreda-ET010103"
    assert updated["source"] == "retained"
    assert [r["level"] for r in updated["hierarchy"]] == ["region", "zone", "woreda"]


def test_unmappable_fictional_level_names_are_preserved(legacy, canonical):
    raw = json.dumps({"hierarchy": [
        {"level_mnemonic": name, "level_value_id": name, "level_value_mnemonic": name.title()}
        for name in ("country", "region", "district", "ward", "village")]})
    assert select("village", raw, legacy, canonical) == ("unmapped", None)


@pytest.mark.parametrize("lowest,raw", [("ET99", ' { "source": 3 } '), ("not-in-catalog", None),
    (None, '{ "lowest_level_value_id" : "not-in-catalog", "source": [4] }'), ("ET", None)])
def test_unmapped_selections_are_preserved_without_update(lowest, raw, legacy, canonical):
    old_levels, old_values = legacy
    old_values["ET99"] = dict(old_values["ET01"], level_value_id="ET99", level_value_mnemonic="Legacy")
    before = (lowest, raw, copy.deepcopy(old_values))
    assert select(lowest, raw, legacy, canonical) == ("unmapped", None)
    assert (lowest, raw, old_values) == before


@pytest.mark.parametrize("lowest,raw", [
    ("ET01", '{"lowest_level_value_id":"region-ET01"}'),
    (None, '{"hierarchy":[]}'), (None, "[]"), (None, '"private-row"'),
    ("", None), (42, None), (None, '{"lowest_level_value_id":false}'),
    ("ET01", '{"hierarchy":null}'), ("ET01", '{"hierarchy":[{}]}'),
    ("ET01", '{"lowest_level_value_id":"ET01","lowest_level_value_id":"ET02"}'),
])
def test_conflicting_or_malformed_selection_rejected(lowest, raw, legacy, canonical):
    with pytest.raises(geo.Refused):
        select(lowest, raw, legacy, canonical)


def test_conflicting_stored_ancestor_rejected(legacy, canonical):
    obj = geo.hierarchy("ET010103", *legacy)
    obj["hierarchy"][1]["level_value_id"] = "ET02"
    with pytest.raises(geo.Refused, match="chain"):
        select("ET010103", json.dumps(obj), legacy, canonical)


def test_unknown_but_well_formed_legacy_hierarchy_is_preserved(legacy, canonical):
    obj = geo.hierarchy("ET010103", *legacy)
    obj["lowest_level_value_id"] = "unknown-legacy"
    obj["hierarchy"][-1]["level_value_id"] = "unknown-legacy"
    raw = json.dumps(obj, indent=3)
    assert select(None, raw, legacy, canonical) == ("unmapped", None)
    obj["hierarchy"][1]["level_mnemonic"] = "woreda"
    assert select(None, json.dumps(obj), legacy, canonical) == ("unmapped", None)


def test_old_catalog_with_exact_ids_and_old_level_ids(legacy, canonical):
    old_levels, _ = legacy
    levels, values, _ = canonical
    row = dict(values["region-ET01"], level_id="l1", parent_level_value_id="ET")
    old_values = {"ET": legacy[1]["ET"], "region-ET01": row}
    aliases = geo.mapping(old_levels, old_values, levels, values)
    raw = json.dumps(geo.hierarchy("region-ET01", levels, values))
    assert geo.selection("region-ET01", raw, aliases, old_levels, old_values, levels, values)[0] == "canonical"


def test_catalog_verification_checks_every_id_parent_label_and_optional_column(canonical):
    levels, values, _ = canonical
    wanted = [levels, values]
    assert geo.catalog_matches(wanted, wanted)
    rc = [{k: {f: v for f, v in row.items() if f not in {"display_name", "version"}}
           for k, row in catalog.items()} for catalog in wanted]
    assert geo.catalog_matches(rc, wanted)
    for field in ("level_value_mnemonic", "parent_level_value_id", "display_name"):
        changed = copy.deepcopy(wanted)
        changed[1]["region-ET01"][field] = "wrong"
        assert not geo.catalog_matches(changed, wanted)
    assert not geo.catalog_matches([], wanted)
    changed = copy.deepcopy(wanted)
    del changed[1]["region-ET01"]["level_value_mnemonic"]
    assert not geo.catalog_matches(changed, wanted)
    changed = copy.deepcopy(wanted)
    del changed[1]["region-ET01"]
    assert not geo.catalog_matches(changed, wanted)


@pytest.mark.parametrize("field,value", [
    ("pcode", "ET01"), ("pcode_source", "COSS"), ("display_name", "Published name"),
    ("display_name_i18n", '{"am":"ክልል"}'), ("version", "2026.10"),
    ("valid_from", "2026-10-15"), ("valid_to", "2027-10-15"),
    ("boundary_uri", "https://example.invalid/full"),
    ("boundary_simplified_uri", "https://example.invalid/simple"), ("source", "Canonical source"),
])
def test_optional_metadata_is_compared_only_when_supported_by_schema(canonical, field, value):
    wanted = [{"level-region": dict(canonical[0]["level-region"])},
              {"region-ET01": dict(canonical[1]["region-ET01"], **{field: value})}]
    current = copy.deepcopy(wanted)
    current[1]["region-ET01"]["server_only_default"] = "not supplied by seed"
    assert geo.catalog_matches(current, wanted)
    current[1]["region-ET01"][field] = None
    assert not geo.catalog_matches(current, wanted)
    del current[1]["region-ET01"][field]  # The RC schema does not expose this optional field.
    assert geo.catalog_matches(current, wanted)


@pytest.mark.parametrize("applied,complete,catalog_ok,changes,ok", [
    (None, False, False, [1], False), ("hash", True, True, [], True),
])
def test_idempotence_success_paths(applied, complete, catalog_ok, changes, ok):
    assert geo.ledger_check(applied, "hash", complete, catalog_ok, changes) is ok


@pytest.mark.parametrize("applied,complete,catalog_ok,changes", [
    ("changed", True, True, []), (None, True, True, []), ("hash", False, True, []),
    ("hash", True, False, []), ("hash", True, True, [1]),
])
def test_idempotence_rejects_hash_drift_missing_completion_catalog_or_reference_drift(applied, complete, catalog_ok, changes):
    with pytest.raises(geo.Refused):
        geo.ledger_check(applied, "hash", complete, catalog_ok, changes)


def test_journal_is_durable_retained_and_requires_matching_completion(tmp_path):
    path = tmp_path / "recovery.json"
    databases = ["master_data_test", "farmer_registry_test"]
    assert not geo.journal_state(path, databases, "hash")
    data = dict(state="prepared", version=geo.VERSION, databases=databases, sha256="hash",
                records=[dict(raw=' { "private": 5 } ', tableoid=123, ctid="(0,1)")])
    geo.persist(path, data, initial=True)
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(geo.Refused, match="Incomplete migration"):
        geo.journal_state(path, databases, "hash")
    with pytest.raises(FileExistsError):
        geo.persist(path, data, initial=True)
    data["state"] = "complete"
    geo.persist(path, data)
    assert geo.journal_state(path, databases, "hash")
    assert json.loads(path.read_text(encoding="utf-8")) == data
    for dbs, digest in ((databases[::-1], "hash"), (databases, "changed")):
        with pytest.raises(geo.Refused, match="mismatch"):
            geo.journal_state(path, dbs, digest)
    path.with_suffix(".tmp").write_text("partial", encoding="utf-8")
    with pytest.raises(geo.Refused, match="Incomplete journal"):
        geo.journal_state(path, databases, "hash")


def test_backup_directory_preflight(tmp_path):
    geo.backup_directory(tmp_path, False)
    with pytest.raises(geo.Refused):
        geo.backup_directory(tmp_path / "absent", False)
    if os.name != "posix":
        pytest.skip("Apply deliberately requires POSIX journal permissions")
    with pytest.raises(FileNotFoundError):
        geo.backup_directory(tmp_path, True)
    for name in ("master-data.dump", "registry.dump"):
        (tmp_path / name).touch()
    with pytest.raises(geo.Refused):
        geo.backup_directory(tmp_path, True)
    for name in ("master-data.dump", "registry.dump"):
        (tmp_path / name).write_bytes(b"test fixture; not a dump")
    geo.backup_directory(tmp_path, True)
    (tmp_path / "registry.dump").unlink()
    (tmp_path / "registry.dump").symlink_to(tmp_path / "master-data.dump")
    with pytest.raises(geo.Refused):
        geo.backup_directory(tmp_path, True)


@pytest.mark.parametrize("extra", [[], ["--apply"], ["--writers-stopped"]])
def test_cli_dry_run_and_apply_acknowledgement(tmp_path, monkeypatch, capsys, extra):
    called = []
    monkeypatch.setattr(geo, "migrate", lambda args: called.append(args))
    args = ["--master-data-db", "master_data", "--registry-db", "farmer_registry", "--journal-dir", str(tmp_path)]
    code = geo.main(args + extra)
    if extra == ["--apply"]:
        assert code == 2 and not called
        assert "--writers-stopped" in capsys.readouterr().err
    else:
        assert code == 0 and not called[0].apply
    assert list(tmp_path.iterdir()) == []


def test_same_database_and_private_exception_rejected_before_output(tmp_path, monkeypatch, capsys):
    args = ["--master-data-db", "same", "--registry-db", "same", "--journal-dir", str(tmp_path)]
    monkeypatch.setattr(geo, "migrate", lambda _: pytest.fail("must not connect"))
    assert geo.main(args) == 2
    args[3] = "other_test"
    def fail(_):
        raise RuntimeError("private-row credentials-must-not-print")
    monkeypatch.setattr(geo, "migrate", fail)
    assert geo.main(args) == 2
    output = capsys.readouterr().err
    assert "RuntimeError" in output
    assert "private-row" not in output and "credentials-must-not-print" not in output


@pytest.mark.skipif(os.name != "posix", reason="Apply requires POSIX journal permissions")
def test_explicit_rehearsal_apply_requires_both_backup_files(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(geo, "migrate", lambda args: called.append(args))
    args = ["--master-data-db", "master_data_test", "--registry-db", "farmer_registry_test",
            "--journal-dir", str(tmp_path), "--apply", "--writers-stopped"]
    assert geo.main(args) == 2 and not called
    (tmp_path / "master-data.dump").write_bytes(b"test fixture; not a dump")
    assert geo.main(args) == 2 and not called
    (tmp_path / "registry.dump").write_bytes(b"test fixture; not a dump")
    assert geo.main(args) == 0 and called[0].apply and called[0].writers_stopped


def test_journal_write_error_leaves_recovery_material(tmp_path, monkeypatch):
    path = tmp_path / "recovery.json"
    data = {"state": "prepared", "records": [{"ctid": "(0,1)", "raw": " {} "}]}
    def fail(_):
        raise OSError("simulated storage failure")
    monkeypatch.setattr(geo.os, "fsync", fail)
    with pytest.raises(OSError):
        geo.persist(path, data, initial=True)
    assert path.exists() and json.loads(path.read_text(encoding="utf-8")) == data
    with pytest.raises(geo.Refused, match="Incomplete migration"):
        geo.journal_state(path, ["master_data", "farmer_registry"], "hash")


def test_incomplete_journal_rejected_without_database_connection(tmp_path, canonical, monkeypatch):
    from types import SimpleNamespace
    args = SimpleNamespace(master_data_db="master_data", registry_db="farmer_registry", journal_dir=tmp_path)
    geo.persist(tmp_path / "recovery.json", {"state": "prepared"}, initial=True)
    # migrate imports the runtime driver lazily, but must never call connect here.
    driver = SimpleNamespace(connect=lambda **_: pytest.fail("must not connect"), sql=None)
    monkeypatch.setitem(sys.modules, "psycopg2", driver)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", SimpleNamespace(Json=None, RealDictCursor=None, execute_values=None))
    monkeypatch.setattr(geo, "canonical", lambda: canonical)
    with pytest.raises(geo.Refused, match="Incomplete migration"):
        geo.migrate(args)
