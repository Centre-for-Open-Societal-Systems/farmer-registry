#!/usr/bin/env python3
"""Prepare an offline review package. Never connect to or modify a database.

Input: the protected staging catalog and aggregate Farmer reference snapshots
used by check-odk-geo-compatibility.py. Output: guarded catalog/index SQL, an exact
diff and unresolved references. Applying the SQL requires separate review;
Farmer reference reconciliation is deliberately not inferred from place names.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("geo_audit", ROOT / "scripts/check-odk-geo-compatibility.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
FIELDS = ("level_value_id", "level_id", "level_value_mnemonic", "parent_level_value_id")


def literal(value):
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def rows_sql(rows, fields):
    return ",\n".join("(" + ",".join(literal(row[field]) for field in fields) + ")" for row in rows)


def prepare(catalog, references):
    expected_levels, expected = audit.canonical_catalog()
    audit.require(isinstance(catalog, dict) and set(catalog) == {"levels", "values"}, "Invalid snapshot")
    levels = audit.index_rows(catalog["levels"], "level_id", {"level_id", "level_mnemonic", "parent_level_id"})
    current = audit.index_rows(catalog["values"], "level_value_id", set(FIELDS))
    audit.require(levels == expected_levels, "Level changes require a different migration")
    audit.require(current.keys() == expected.keys(), "Missing/extra IDs require a different migration")
    audit.require(all(current[key]["level_id"] == expected[key]["level_id"] for key in current),
                  "Level reassignment requires a different migration")
    # Invalid current parents are the defect being repaired, so do not require
    # the input catalog to have valid parent chains. The canonical target does.
    differences = [{"before": current[key], "after": expected[key]} for key in sorted(current)
                   if any(current[key][field] != expected[key][field] for field in FIELDS)]
    summary = audit.reference_summary(references, expected)
    unresolved = [row for row in references if row["geo_lowest_level_value_id"] not in expected]
    canonical = [expected[key] for key in sorted(expected)]
    old_rows = [item["before"] for item in differences]
    level_fields = ("level_id", "level_mnemonic", "parent_level_id")
    sql = """-- REVIEW PACKAGE ONLY: no authorization to apply is implied.
-- Catalog fields and reviewed mnemonic index only; no IDs are replaced and
-- no Farmer records are updated. Global name uniqueness is incompatible with
-- canonical same-named places in different parents; retain sibling uniqueness.
-- Rehearse on a restored master_data database, inventory every consumer, and
-- obtain review before applying during an approved shared maintenance window.
\\set ON_ERROR_STOP on
BEGIN ISOLATION LEVEL SERIALIZABLE;
SET LOCAL lock_timeout = '5s';
SET LOCAL standard_conforming_strings = on;
LOCK TABLE public.g2p_geo_levels, public.g2p_geo_level_values IN SHARE ROW EXCLUSIVE MODE;
CREATE TEMP TABLE farmer_geo_expected (
 level_value_id text PRIMARY KEY, level_id text NOT NULL,
 level_value_mnemonic text NOT NULL, parent_level_value_id text
) ON COMMIT DROP;
CREATE TEMP TABLE farmer_geo_before (LIKE farmer_geo_expected INCLUDING ALL) ON COMMIT DROP;
CREATE TEMP TABLE farmer_geo_levels (
 level_id text PRIMARY KEY, level_mnemonic text NOT NULL, parent_level_id text
) ON COMMIT DROP;
"""
    sql += "INSERT INTO farmer_geo_expected VALUES\n" + rows_sql(canonical, FIELDS) + ";\n"
    sql += "INSERT INTO farmer_geo_levels VALUES\n" + rows_sql(list(expected_levels.values()), level_fields) + ";\n"
    if old_rows:
        sql += "INSERT INTO farmer_geo_before VALUES\n" + rows_sql(old_rows, FIELDS) + ";\n"
    projection = ",".join(FIELDS)
    exact = f"""NOT EXISTS (
 (SELECT {projection} FROM public.g2p_geo_level_values EXCEPT SELECT * FROM farmer_geo_expected)
 UNION ALL
 (SELECT * FROM farmer_geo_expected EXCEPT SELECT {projection} FROM public.g2p_geo_level_values)
)"""
    sql += """DO $farmer_geo_repair$
DECLARE changed integer;
BEGIN
 IF current_database() <> 'master_data' THEN
  RAISE EXCEPTION 'Expected an explicitly isolated or approved master_data database';
 END IF;
 IF EXISTS (SELECT 1 FROM pg_trigger
            WHERE tgrelid='public.g2p_geo_level_values'::regclass
              AND NOT tgisinternal AND tgenabled<>'D') THEN
  RAISE EXCEPTION 'Unreviewed catalog trigger; use a separately reviewed procedure';
 END IF;
 IF EXISTS (
  (SELECT level_id,level_mnemonic,parent_level_id FROM public.g2p_geo_levels EXCEPT SELECT * FROM farmer_geo_levels)
  UNION ALL
  (SELECT * FROM farmer_geo_levels EXCEPT SELECT level_id,level_mnemonic,parent_level_id FROM public.g2p_geo_levels)
 ) THEN RAISE EXCEPTION 'Geography levels changed since review'; END IF;
 IF to_regclass('public.ux_geo_level_values_mnemonic') IS NOT NULL THEN
  IF pg_get_indexdef('public.ux_geo_level_values_mnemonic'::regclass) <>
   'CREATE UNIQUE INDEX ux_geo_level_values_mnemonic ON public.g2p_geo_level_values USING btree (level_value_mnemonic)'
  THEN RAISE EXCEPTION 'Unexpected global mnemonic index definition'; END IF;
  DROP INDEX public.ux_geo_level_values_mnemonic;
 END IF;
 IF to_regclass('public.ux_geo_level_values_sibling_mnemonic') IS NULL THEN
  CREATE UNIQUE INDEX ux_geo_level_values_sibling_mnemonic
   ON public.g2p_geo_level_values (level_id,parent_level_value_id,level_value_mnemonic) NULLS NOT DISTINCT;
 ELSIF pg_get_indexdef('public.ux_geo_level_values_sibling_mnemonic'::regclass) <>
  'CREATE UNIQUE INDEX ux_geo_level_values_sibling_mnemonic ON public.g2p_geo_level_values USING btree (level_id, parent_level_value_id, level_value_mnemonic) NULLS NOT DISTINCT'
 THEN RAISE EXCEPTION 'Unexpected sibling mnemonic index definition'; END IF;
"""
    sql += f" IF {exact} THEN RETURN; END IF;\n"
    sql += """ UPDATE public.g2p_geo_level_values AS live
 SET level_value_mnemonic=target.level_value_mnemonic,
     parent_level_value_id=target.parent_level_value_id
 FROM farmer_geo_before AS old
 JOIN farmer_geo_expected AS target USING (level_value_id)
 WHERE live.level_value_id=old.level_value_id
   AND live.level_id IS NOT DISTINCT FROM old.level_id
   AND live.level_value_mnemonic IS NOT DISTINCT FROM old.level_value_mnemonic
   AND live.parent_level_value_id IS NOT DISTINCT FROM old.parent_level_value_id;
 GET DIAGNOSTICS changed = ROW_COUNT;
"""
    sql += f" IF changed <> {len(old_rows)} THEN RAISE EXCEPTION 'Catalog changed since review'; END IF;\n"
    sql += f" IF NOT ({exact}) THEN RAISE EXCEPTION 'Catalog does not match the reviewed canonical target'; END IF;\n"
    sql += "END;\n$farmer_geo_repair$;\nCOMMIT;\n"
    manifest = {"environment": "staging", "database": "master_data", "applyAuthorized": False,
                "catalogRowsChanged": len(differences), "idsAddedOrRemoved": 0,
                "parentChanges": sum(r["before"]["parent_level_value_id"] != r["after"]["parent_level_value_id"] for r in differences),
                "labelChanges": sum(r["before"]["level_value_mnemonic"] != r["after"]["level_value_mnemonic"] for r in differences),
                "schemaChange": {"replaceIndex": "ux_geo_level_values_mnemonic",
                                 "withIndex": "ux_geo_level_values_sibling_mnemonic",
                                 "uniqueColumns": ["level_id", "parent_level_value_id", "level_value_mnemonic"],
                                 "nullsNotDistinct": True},
                "farmerReferences": summary, "farmerReferenceUpdatesIncluded": False,
                "requiredBeforeApply": ["restored-database rehearsal", "all-consumer impact review",
                                        "fresh verified backups", "approved shared maintenance window",
                                        "separate Farmer reference reconciliation", "explicit repair approval"]}
    return manifest, differences, unresolved, sql


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new protected review directory")
    args = parser.parse_args()
    manifest, differences, unresolved, sql = prepare(audit.read_json(args.catalog), audit.read_json(args.references))
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, value in (("review.json", manifest), ("catalog-diff.json", differences), ("unresolved-references.json", unresolved)):
        path = args.output / name
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
    path = args.output / "catalog-repair.sql"
    path.write_text(sql, encoding="utf-8")
    path.chmod(0o600)
    print(json.dumps(manifest))


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Exception:
        raise SystemExit("Repair preparation failed; protected snapshots/output were not printed")
