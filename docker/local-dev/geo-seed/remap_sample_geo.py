#!/usr/bin/env python3
"""Point every already-seeded Farmer/Household row at a real Ethiopia kebele.

load_sample_data.py's ~500-row fixture comes from the shared registry-platform
demography CSVs (the generic "Kamuntu" sample-pack country), so its own
master-data geo resolution never matches real Ethiopia data — there is no
"Kamuntu" region to look up. Rather than replace that shared fixture, this
runs after it and reassigns every row to a random real kebele from whatever
Ethiopia hierarchy ethiopia_geo_seed.sql.gz just loaded into master-data, so
the Location tab and region/zone/woreda/kebele columns show real places.

Idempotent and safe to rerun: every row is simply reassigned again.
"""

import json
import os
import random

import psycopg2
import psycopg2.extras

LEVEL_ALIASES = {
    "region": "region",
    "zone": "zone",
    "district": "zone",
    "woreda": "woreda",
    "ward": "woreda",
    "kebele": "kebele",
    "village": "kebele",
}


def connect(prefix: str):
    return psycopg2.connect(
        host=os.environ[f"{prefix}_PGHOST"],
        port=os.environ.get(f"{prefix}_PGPORT", "5432"),
        dbname=os.environ[f"{prefix}_PGDATABASE"],
        user=os.environ[f"{prefix}_PGUSER"],
        password=os.environ[f"{prefix}_PGPASSWORD"],
    )


def main():
    md_conn = connect("MD")
    reg_conn = connect("REGISTRY")

    with md_conn.cursor() as cur:
        cur.execute("SELECT level_id, level_mnemonic FROM g2p_geo_levels")
        level_mnemonic = dict(cur.fetchall())
        cur.execute(
            "SELECT level_value_id, level_id, level_value_mnemonic,"
            " parent_level_value_id, display_name FROM g2p_geo_level_values"
        )
        by_id = {
            row[0]: {"level_id": row[1], "mnemonic": row[2], "parent": row[3], "name": row[4]}
            for row in cur.fetchall()
        }
    md_conn.close()

    kebele_ids = [
        vid for vid, row in by_id.items() if level_mnemonic.get(row["level_id"]) == "kebele"
    ]
    if not kebele_ids:
        print("[remap-sample-geo] no kebeles in master-data — nothing to do.")
        return
    print(f"[remap-sample-geo] {len(by_id)} geo values loaded, {len(kebele_ids)} kebeles available.")

    def chain_for(kebele_id: str):
        chain, cur_id, seen = [], kebele_id, set()
        while cur_id and cur_id in by_id and cur_id not in seen:
            seen.add(cur_id)
            chain.append((cur_id, by_id[cur_id]))
            cur_id = by_id[cur_id]["parent"]
        chain.reverse()
        return chain

    def hierarchy_and_names(kebele_id: str):
        chain = chain_for(kebele_id)
        hierarchy = [
            {
                "level_mnemonic": level_mnemonic.get(row["level_id"]),
                "level_value_id": vid,
                "level_value_mnemonic": row["mnemonic"],
            }
            for vid, row in chain
        ]
        names = {"region": None, "zone": None, "woreda": None, "kebele": None}
        for _vid, row in chain:
            target = LEVEL_ALIASES.get(level_mnemonic.get(row["level_id"]))
            if target:
                names[target] = row["name"]
        return {"hierarchy": hierarchy}, names

    random.seed(int(os.environ.get("GEO_REMAP_SEED", "42")))

    with reg_conn.cursor() as cur:
        cur.execute("SELECT internal_record_id FROM g2p_register_farmers")
        farmer_ids = [row[0] for row in cur.fetchall()]
    print(f"[remap-sample-geo] updating {len(farmer_ids)} farmer rows")
    with reg_conn.cursor() as cur:
        for rid in farmer_ids:
            kebele_id = random.choice(kebele_ids)
            hierarchy, names = hierarchy_and_names(kebele_id)
            cur.execute(
                "UPDATE g2p_register_farmers SET geo_lowest_level_value_id = %s,"
                " geo_code_hierarchy_json = %s, region_name = %s, zone_name = %s,"
                " woreda_name = %s, kebele_name = %s WHERE internal_record_id = %s",
                (
                    kebele_id,
                    psycopg2.extras.Json(hierarchy),
                    names["region"],
                    names["zone"],
                    names["woreda"],
                    names["kebele"],
                    rid,
                ),
            )
    reg_conn.commit()

    with reg_conn.cursor() as cur:
        cur.execute("SELECT internal_record_id FROM g2p_register_households")
        household_ids = [row[0] for row in cur.fetchall()]
    print(f"[remap-sample-geo] updating {len(household_ids)} household rows")
    with reg_conn.cursor() as cur:
        for rid in household_ids:
            kebele_id = random.choice(kebele_ids)
            hierarchy, _names = hierarchy_and_names(kebele_id)
            cur.execute(
                "UPDATE g2p_register_households SET geo_lowest_level_value_id = %s,"
                " geo_code_hierarchy_json = %s WHERE internal_record_id = %s",
                (kebele_id, psycopg2.extras.Json(hierarchy), rid),
            )
    reg_conn.commit()
    reg_conn.close()
    print("[remap-sample-geo] done")


if __name__ == "__main__":
    main()
