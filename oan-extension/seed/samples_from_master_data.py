#!/usr/bin/env python3
"""Write the farmer seed's sample people from Master Data's.

The farmer db-seed submits sample households and farmers through the intake
API, reading them from <OPENG2P_DATA_DIR>/demography/{households,individuals}.csv
(load_sample_data.py). Those files are the Kamuntu demo. Master Data holds the
country pack's own sample people (g2p_sample_households, g2p_sample_individuals,
loaded from the pack's samples/ by the master-data seed), each on a unit of the
pack's geography. This writes them in the loader's CSV format, so the registry
seeds the same people as Master Data and the pack stays the only source.

Names: an Ethiopian name is the person's, the father's and the grandfather's.
The pack gives the first two, which become first and middle name. The
grandfather's name, which the form requires, is taken from the pack's own male
given names, the same one for a person on every run.

Usage: samples_from_master_data.py <output dir>   (reads MD_PG* like the seed)
"""

import csv
import json
import os
import sys
import zlib
from pathlib import Path

import psycopg2
import psycopg2.extras

INDIVIDUAL_COLUMNS = [
    "internal_record_id", "functional_record_id", "household_id", "first_name", "middle_name",
    "last_name", "full_name", "given_name", "gender", "birth_date", "estimated_age",
    "marital_status", "phone_numbers", "foundational_id", "education_level", "latitude",
    "longitude", "address_line_1", "country_code", "geo_pcode",
]
HOUSEHOLD_COLUMNS = [
    "internal_record_id", "functional_record_id", "head_individual_id", "head_name",
    "headship_type", "size_total", "number_of_female_members", "number_of_male_members",
    "latitude", "longitude", "address_line_1", "country_code", "geo_pcode",
]


def connect():
    return psycopg2.connect(
        host=os.environ["MD_PGHOST"],
        port=os.environ.get("MD_PGPORT", "5432"),
        dbname=os.environ["MD_PGDATABASE"],
        user=os.environ.get("MD_PGUSER", ""),
        password=os.environ.get("MD_PGPASSWORD", ""),
    )


def address(parts) -> str:
    return ", ".join(str(v) for v in (parts or {}).values() if v)


def country_code(alpha3: str | None) -> str:
    return {"ETH": "ET"}.get(alpha3 or "", (alpha3 or "")[:2])


def main(out: Path) -> int:
    with connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM g2p_sample_individuals ORDER BY individual_id")
        people = cur.fetchall()
        cur.execute("SELECT * FROM g2p_sample_households ORDER BY household_id")
        households = cur.fetchall()
    if not people:
        print("[oan-samples] Master Data has no sample people; the farmer seed's own are used.")
        return 1

    male_names = sorted({p["given_name"] for p in people if p["gender"] == "MALE" and p["given_name"]})
    individuals = []
    for p in people:
        father = p["fathers_name"] or ""
        pool = [n for n in male_names if n not in (father, p["given_name"])] or male_names
        grandfather = pool[zlib.crc32(p["individual_id"].encode()) % len(pool)]
        full_name = " ".join(n for n in (p["given_name"], father, grandfather) if n)
        individuals.append({
            "internal_record_id": p["individual_id"],
            "functional_record_id": p["individual_id"],
            "household_id": p["household_id"],
            "first_name": p["given_name"],
            "middle_name": father,
            "last_name": grandfather,
            "full_name": full_name,
            "given_name": p["given_name"],
            "gender": p["gender"],
            "birth_date": p["birth_date"].isoformat() if p["birth_date"] else "",
            "estimated_age": p["age"] or "",
            "marital_status": p["marital_status"] or "",
            "phone_numbers": json.dumps(
                [{"type": "mobile", "number": p["phone"], "is_primary": True}] if p["phone"] else []),
            "foundational_id": p["national_id"] or "",
            "education_level": p["education_level"] or "",
            "latitude": p["latitude"] if p["latitude"] is not None else "",
            "longitude": p["longitude"] if p["longitude"] is not None else "",
            "address_line_1": address(p["address_parts"]),
            "country_code": country_code(p["country"]),
            "geo_pcode": p["geo_pcode"] or "",
        })

    by_id = {i["internal_record_id"]: i for i in individuals}
    rows = []
    for h in households:
        members = [i for i in individuals if i["household_id"] == h["household_id"]]
        head = by_id.get(h["head_individual_id"]) or (members[0] if members else None)
        if not head:
            continue
        rows.append({
            "internal_record_id": h["household_id"],
            "functional_record_id": h["household_id"],
            "head_individual_id": head["internal_record_id"],
            "head_name": head["full_name"],
            "headship_type": h["headship_type"] or "",
            "size_total": h["size_total"] or len(members),
            "number_of_female_members": sum(m["gender"] == "FEMALE" for m in members),
            "number_of_male_members": sum(m["gender"] == "MALE" for m in members),
            "latitude": h["latitude"] if h["latitude"] is not None else "",
            "longitude": h["longitude"] if h["longitude"] is not None else "",
            "address_line_1": address(h["address_parts"]),
            "country_code": country_code(h["country"]),
            "geo_pcode": h["geo_pcode"] or "",
        })

    demography = out / "demography"
    demography.mkdir(parents=True, exist_ok=True)
    for name, columns, data in (("individuals.csv", INDIVIDUAL_COLUMNS, individuals),
                                ("households.csv", HOUSEHOLD_COLUMNS, rows)):
        with open(demography / name, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(data)
    print(f"[oan-samples] {len(individuals)} people in {len(rows)} households from Master Data.")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
