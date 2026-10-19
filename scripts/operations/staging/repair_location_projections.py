#!/usr/bin/env python3
"""Audited repair of Farmer staging location projections; never seed geography."""
import argparse
import hashlib
import json
import os
from pathlib import Path

LEVEL_FIELDS = ("level_id", "level_mnemonic", "parent_level_id")
VALUE_FIELDS = ("level_value_id", "level_id", "parent_level_value_id", "level_value_mnemonic")
CANONICAL_SHA256 = "e1cc3e5ce67fe4d8e3978eea1102f63ee7a1e18ecb02c4910a53e1126e623dde"


def normalize_catalog(catalog):
    return {
        "levels": sorted(({k: r[k] for k in LEVEL_FIELDS} for r in catalog["levels"]), key=lambda r: r["level_id"]),
        "values": sorted(({k: r[k] for k in VALUE_FIELDS} for r in catalog["values"]), key=lambda r: r["level_value_id"]),
    }


def catalog_digest(catalog):
    return hashlib.sha256(json.dumps(normalize_catalog(catalog), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def hierarchy_for(index, leaf):
    chain, current = [], leaf
    while current:
        node = index[current]
        chain.append({"level_mnemonic": node["level_id"].removeprefix("level-"),
                      "level_value_mnemonic": node["level_value_mnemonic"], "level_value_id": current})
        current = node["parent_level_value_id"]
    chain.reverse()
    if [n["level_mnemonic"] for n in chain] != ["region", "zone", "woreda", "kebele"]:
        raise ValueError("Incomplete canonical geography")
    return chain


def projections(chain):
    return {**{node["level_mnemonic"] + "_name": node["level_value_mnemonic"] for node in chain},
            "woreda_level_value_id": chain[2]["level_value_id"],
            "geo_code_hierarchy_json": {"hierarchy": chain}}


def check_database(cur, rehearsal):
    cur.execute("SELECT current_database()")
    db = cur.fetchone()[0]
    if not (db.startswith("farmer_seed_rehearsal_") if rehearsal else db == "farmer_registry_far"):
        raise ValueError("Refusing a database outside the explicit staging/rehearsal target")


def repair_projections(connection, catalog, audit_path, *, rehearsal=False, dry_run=True):
    """Repair only derived labels/hierarchy; preserve chosen IDs and other data."""
    from psycopg2 import sql
    from psycopg2.extras import Json
    if catalog_digest(catalog) != CANONICAL_SHA256:
        raise ValueError("Catalog differs from the canonical COSS Ethiopia geo_seed")
    index = {r["level_value_id"]: r for r in catalog["values"]}
    with connection:
        with connection.cursor() as cur:
            check_database(cur, rehearsal)
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute("SET LOCAL statement_timeout='60s'")
            cur.execute("LOCK TABLE g2p_register_farmers IN SHARE ROW EXCLUSIVE MODE")
            cur.execute("SELECT to_jsonb(f) FROM g2p_register_farmers f WHERE geo_lowest_level_value_id IS NOT NULL ORDER BY internal_record_id")
            repairs = []
            for (before,) in cur.fetchall():
                leaf = before["geo_lowest_level_value_id"]
                if leaf not in index or before.get("country_code") not in (None, "ET"):
                    raise ValueError("Noncanonical existing Farmer location; reconcile separately")
                desired = projections(hierarchy_for(index, leaf))
                if any(before.get(k) != v for k, v in desired.items()):
                    repairs.append({"internal_record_id": before["internal_record_id"],
                                    "before": {k: before.get(k) for k in desired}, "after": desired})
            if dry_run:
                return {"plannedRepairs": len(repairs), "repaired": 0}
            # Export only the fields being repaired, before making any writes.
            # No overwriting an earlier audit file, even on a rerun.
            fd = os.open(audit_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"catalogSha256": CANONICAL_SHA256, "repairs": repairs}, stream, ensure_ascii=False)
            for repair in repairs:
                changes = repair["after"]
                query = sql.SQL("UPDATE g2p_register_farmers SET {} WHERE internal_record_id=%s").format(
                    sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(k)) for k in changes))
                cur.execute(query, tuple(Json(v) if isinstance(v, dict) else v for v in changes.values()) + (repair["internal_record_id"],))
                if cur.rowcount != 1:
                    raise RuntimeError("Location repair target changed")
    return {"repaired": len(repairs), "catalogSha256": CANONICAL_SHA256}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["staging"])
    parser.add_argument("--namespace", required=True, choices=["far"])
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rehearsal", action="store_true")
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args()
    if args.apply and not args.audit:
        parser.error("Applying location repairs requires --audit")
    import psycopg2
    connection = psycopg2.connect("")
    try:
        result = repair_projections(connection, json.loads(args.catalog.read_text(encoding="utf-8")),
                                    args.audit, rehearsal=args.rehearsal, dry_run=not args.apply)
    finally:
        connection.close()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
