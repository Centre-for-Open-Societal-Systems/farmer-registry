#!/usr/bin/env python3
"""Import the official OpenG2P ETH pack: 21 people and 6 households.

Explicit staging operator workflow, never the metadata deployment hook. Keep
source GPS coordinates but leave catalog IDs/Kebele unassigned: the pack uses
OCHA Woreda codes, which are not canonical COSS Kebele IDs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

MARKER = "openg2p-eth-samples-v1"
NAMESPACE = uuid.UUID("b9294bb3-4322-441e-8ddb-e687fe8a087b")
SOURCE_SHA256 = "6b991492a3b82a6630c8a2388230355f34bccc57b96c1df89bf2cfe1fdd77bad"


def source_digest(people, households):
    return hashlib.sha256(json.dumps({"individuals": people, "households": households}, sort_keys=True,
                                     ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def identity(source_id):
    return str(uuid.uuid5(NAMESPACE, source_id))


def generate(people, households):
    if len(people) != 21 or len(households) != 6 or source_digest(people, households) != SOURCE_SHA256:
        raise ValueError("Official ETH sample files differ from the reviewed 21-person/6-household pack")
    by_id = {p["individual_id"]: p for p in people}
    hh_ids = {h["household_id"] for h in households}
    if len(by_id) != 21 or len(hh_ids) != 6:
        raise ValueError("Duplicate official sample IDs")
    def common(source_id, name, row):
        return {"internal_record_id": identity(source_id), "functional_record_id": source_id,
                "record_name": name + " (OpenG2P sample)", "created_by": MARKER,
                "last_approved_by": MARKER, "record_status": "ACTIVE", "country_code": "ET",
                "latitude": row["latitude"], "longitude": row["longitude"],
                "search_text": source_id + " " + name + " OpenG2P sample",
                "geo_lowest_level_value_id": None, "geo_code_hierarchy_json": None,
                "address_line_1": ", ".join(str(v) for k, v in row.get("address_parts", {}).items() if k != "kebele" and v)}
    farmers = []
    for person in people:
        if person["household_id"] not in hh_ids:
            raise ValueError("Official person references an unknown household")
        farmers.append({**common(person["individual_id"], person["full_name"], person),
                        "link_internal_record_id": identity(person["household_id"]),
                        "first_name": person["given_name"], "given_name": person["given_name"],
                        "middle_name": person.get("fathers_name"), "father_first_name": person.get("fathers_name"),
                        "gender": person["gender"], "birth_date": person["birth_date"],
                        "state": "APPROVED", "import_source": "IMPORT_FILE"})
    groups = []
    for household in households:
        head = by_id.get(household["head_individual_id"])
        if head is None or head["household_id"] != household["household_id"]:
            raise ValueError("Official household head is inconsistent")
        members = [p for p in people if p["household_id"] == household["household_id"]]
        if len(members) != household["size_total"]:
            raise ValueError("Official household member count is inconsistent")
        groups.append({**common(household["household_id"], head["full_name"] + " household", household),
                       "household_head": head["full_name"], "size_of_group": household["size_total"],
                       "number_of_female_members": sum(p["gender"] == "FEMALE" for p in members),
                       "number_of_male_members": sum(p["gender"] == "MALE" for p in members)})
    return {"g2p_register_farmers": farmers, "g2p_register_households": groups}


def apply(connection, records, *, rehearsal=False, fail_after_insert=False):
    from psycopg2 import sql
    from psycopg2.extras import execute_values
    counts = {"g2p_register_farmers": 21, "g2p_register_households": 6}
    if set(records) != set(counts) or any(len(records[t]) != n for t, n in counts.items()):
        raise ValueError("Expected official 21-person/6-household set")
    inserted = {}
    with connection:
        with connection.cursor() as cur:
            cur.execute("SELECT current_database()")
            db = cur.fetchone()[0]
            if not (db.startswith("farmer_seed_rehearsal_") if rehearsal else db == "farmer_registry_far"):
                raise ValueError("Database is outside the explicit staging/rehearsal target")
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute("SET LOCAL statement_timeout='60s'")
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (MARKER,))
            cur.execute("LOCK TABLE g2p_register_farmers, g2p_register_households IN SHARE ROW EXCLUSIVE MODE")
            snapshots = {}
            for table in counts:
                cur.execute(sql.SQL("SELECT to_jsonb(t) FROM {} t WHERE created_by<>%s ORDER BY internal_record_id").format(sql.Identifier(table)), (MARKER,))
                snapshots[table] = cur.fetchall()
            # Households first, to keep declared Farmer links resolvable.
            for table in reversed(counts):
                rows = records[table]
                cur.execute(sql.SQL("SELECT to_jsonb(t) FROM {} t WHERE created_by=%s ORDER BY internal_record_id").format(sql.Identifier(table)), (MARKER,))
                existing = {r[0]["internal_record_id"]: r[0] for r in cur.fetchall()}
                if existing:
                    if len(existing) != len(rows) or any(any(existing.get(r["internal_record_id"], {}).get(k) != v for k, v in r.items()) for r in rows):
                        raise ValueError("Existing official sample set changed; reconcile without overwriting")
                    inserted[table] = 0
                    continue
                # Refuse source-ID collisions with records owned by other workflows.
                cur.execute(sql.SQL("SELECT count(*) FROM {} WHERE functional_record_id=ANY(%s)").format(sql.Identifier(table)), ([r["functional_record_id"] for r in rows],))
                if cur.fetchone()[0]:
                    raise ValueError("Official sample ID conflicts with an existing record")
                columns = list(rows[0]) + ["created_at", "last_approved_at"]
                stamp = datetime.now(timezone.utc).replace(tzinfo=None)
                values = [tuple(r[k] for k in rows[0]) + (stamp, stamp) for r in rows]
                query = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, columns)))
                execute_values(cur, query.as_string(cur), values)
                inserted[table] = len(rows)
            if fail_after_insert:
                raise RuntimeError("Injected official sample import failure")
            for table in counts:
                cur.execute(sql.SQL("SELECT to_jsonb(t) FROM {} t WHERE created_by<>%s ORDER BY internal_record_id").format(sql.Identifier(table)), (MARKER,))
                if cur.fetchall() != snapshots[table]:
                    raise RuntimeError("Pre-existing data changed")
    return {"insertedFarmers": inserted["g2p_register_farmers"], "insertedHouseholds": inserted["g2p_register_households"],
            "officialFarmers": 21, "officialHouseholds": 6, "kebeleAssigned": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["staging"])
    parser.add_argument("--namespace", required=True, choices=["far"])
    parser.add_argument("--pack", type=Path, default=Path("/openg2p-data/packs/ETH"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rehearsal", action="store_true")
    args = parser.parse_args()
    records = generate(json.loads((args.pack / "samples/individuals.json").read_text()),
                       json.loads((args.pack / "samples/households.json").read_text()))
    if not args.apply:
        print(json.dumps({"plannedFarmers": 21, "plannedHouseholds": 6, "sourceSha256": SOURCE_SHA256, "kebeleAssigned": False}))
        return
    import psycopg2
    connection = psycopg2.connect("")
    try:
        print(json.dumps(apply(connection, records, rehearsal=args.rehearsal)))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
