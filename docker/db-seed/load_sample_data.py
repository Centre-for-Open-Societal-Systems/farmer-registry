#!/usr/bin/env python3
"""Load the Farmer Registry's sample data (db-seed, LOAD_SAMPLE_DATA=true).

As the OpenG2P docs describe a registry's sample loader (Country data & seeding;
Farmer Registry, Data seeding):

- The sample people and households are Master Data's, read through its API
  (/samples, with the MDS_* client-credentials settings the chart passes),
  never its database. They come from the country pack's samples/.
- The registry's own facts about them (grandfather's name, lands, crops,
  livestock, farm inputs, cooperative membership) are the same pack's
  samples/farms.json, in the openg2p-data checkout this image carries
  (OPENG2P_DATA_DIR).
- Records are written as approved sample records into this registry's own
  tables, numbered like the sample people: ETH-IND-0007 is farmer FR-0007,
  whose lands are LAND-0007-1, LAND-0007-2, located where the person lives.

No staff account signs in and no approval task is opened or decided: the loader
holds no Keycloak user credentials and calls no registry API. Its only network
reads are Master Data's.

Idempotent: record ids are derived from the pack ids, and every insert is
ON CONFLICT DO NOTHING. A person whose Fayda ID a farmer already holds (or
awaits approval with) is skipped, and a household one of whose members is
already registered is not created again; its new farmers join that household.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mds_client  # noqa: E402  (the registry platform's Master Data client)

SEEDER = "seeder"
PACK = os.environ.get("SAMPLE_PACK", "ETH-OAN")
OPENG2P_DATA_DIR = Path(os.environ.get("OPENG2P_DATA_DIR", "/openg2p-data"))
COUNTRY_CODE = {"ETH": "ET"}
DIAL_CODE = {"ET": "+251"}
# Stable ids: the same pack person always becomes the same record.
_IDS = uuid.UUID("6f1c2a52-3b8e-4d0e-9a51-0c7e5b1f2d34")
_QUEUE = uuid.UUID("a1b2c3d4-0000-4000-8000-000000000002")


def log(message: str) -> None:
    print(f"[load-sample-data] {message}", flush=True)


def record_id(kind: str, key: str) -> str:
    return str(uuid.uuid5(_IDS, f"{kind}:{key}"))


def number(pack_id: str) -> str:
    """ETH-IND-0007 -> 0007; ETH-HH-001 -> 0001."""
    return pack_id.rsplit("-", 1)[-1].zfill(4)


def words(*parts) -> str:
    return " ".join(str(p) for p in parts if p not in (None, ""))


def parse_date(value) -> date | None:
    if isinstance(value, date) or not value:
        return value or None
    return date.fromisoformat(str(value)[:10])


def age_on(person: dict, today: date) -> int | None:
    born = parse_date(person.get("birth_date"))
    if born is None:
        return person.get("age")
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


class Geography:
    """Records' location fields for a P-code, from Master Data's geography."""

    def __init__(self, chain_of):
        self._chain_of = chain_of
        self._cache: dict[str, dict] = {}

    def location(self, pcode: str) -> dict:
        if pcode not in self._cache:
            chain = self._chain_of(pcode)
            if not chain:
                raise RuntimeError(f"{pcode} is not a unit of Master Data's published geography")
            hierarchy = [{
                "level": u["level_mnemonic"], "level_id": u["level_id"], "level_mnemonic": u["level_mnemonic"],
                "level_value_id": u["unit_id"], "level_value_mnemonic": u["name"],
            } for u in chain]
            self._cache[pcode] = {
                "geo_lowest_level_value_id": pcode,
                "geo_code_hierarchy_json": {"hierarchy": hierarchy, "lowest_level_value_id": pcode},
                "names": {u["level_mnemonic"]: u["name"] for u in chain},
            }
        return self._cache[pcode]


def address(record: dict) -> dict:
    country = COUNTRY_CODE.get(record.get("country") or "ETH", record.get("country"))
    parts = record.get("address_parts") or {}
    return {
        "address_line_1": words(*parts.values()) or None,
        "latitude": record.get("latitude"), "longitude": record.get("longitude"),
        "country_code": country,
    }


def phone(person: dict, kind: str) -> dict | None:
    e164 = person.get("phone")
    if not e164:
        return None
    country = COUNTRY_CODE.get(person.get("country") or "ETH", "ET")
    dial = DIAL_CODE.get(country, "")
    national = e164[len(dial):] if dial and e164.startswith(dial) else e164.lstrip("+")
    return {"phone_type": kind, "phone_number": national, "country_code": country,
            "is_primary": True, "phone_e164": e164}


def common(internal_id: str, functional_id: str | None, link: str | None, name: str,
           search: str, now: datetime) -> dict:
    return {
        "internal_record_id": internal_id, "functional_record_id": functional_id,
        "link_internal_record_id": link, "record_name": name,
        "created_by": SEEDER, "created_at": now, "last_approved_at": now, "last_approved_by": SEEDER,
        "search_text": search, "record_status": "ACTIVE",
    }


def plan(people: list[dict], households: list[dict], farms: dict, geo: Geography,
         registered: set, member_households: dict, now: datetime) -> dict[str, list[dict]]:
    """Rows to insert, by table. Nothing here touches a database or a network."""
    today = now.date()
    rows: dict[str, list[dict]] = {t: [] for t in (
        "g2p_register_households", "g2p_register_household_members", "g2p_register_farmers",
        "g2p_register_farmer_phones", "g2p_register_lands", "g2p_register_crops",
        "g2p_register_livestocks", "g2p_register_farm_inputs", "g2p_register_membership_details")}
    unknown = sorted(set(farms) - {p["individual_id"] for p in people})
    if unknown:
        raise RuntimeError(f"farms.json names people Master Data does not hold: {unknown}")

    for household in households:
        members = [p for p in people if p.get("household_id") == household["household_id"]]
        if not members:
            continue
        head = next((m for m in members if m["individual_id"] == household.get("head_individual_id")), None)
        if head is None:
            raise RuntimeError(f"household {household['household_id']} names a head who is not among its people")
        names = {m["individual_id"]: (m.get("given_name"), m.get("fathers_name"),
                                      ((farms.get(m["individual_id"]) or {}).get("farmer") or {}).get("grandfathers_name"))
                 for m in members}
        existing = next((member_households[m["national_id"]] for m in members
                         if m.get("national_id") in member_households), None)
        household_id = existing or record_id("household", household["household_id"])
        created = existing is None
        if created:
            place = geo.location(household["geo_pcode"])
            ages = [age_on(m, today) for m in members]
            head_name = words(*names[head["individual_id"]])
            functional = "HH-" + number(household["household_id"])
            rows["g2p_register_households"].append({
                **common(household_id, functional, None, head_name, words(functional, head_name), now),
                **address(household),
                "geo_lowest_level_value_id": place["geo_lowest_level_value_id"],
                "geo_code_hierarchy_json": place["geo_code_hierarchy_json"],
                "household_head": head_name,
                "size_of_group": len(members),
                "number_of_children": sum(a is not None and a < 18 for a in ages),
                "number_of_elderly_members": sum(a is not None and a >= 60 for a in ages),
                "number_of_female_members": sum(m.get("gender") == "FEMALE" for m in members),
                "number_of_male_members": sum(m.get("gender") == "MALE" for m in members),
                "other_land_owner": False,
            })
            for m in members:
                first, middle, last = names[m["individual_id"]]
                place = geo.location(m["geo_pcode"])
                functional = "HM-" + number(m["individual_id"])
                rows["g2p_register_household_members"].append({
                    **common(record_id("member", m["individual_id"]), functional, household_id,
                             words(first, last), words(functional, first, middle, last, m.get("national_id")), now),
                    **address(m),
                    "geo_lowest_level_value_id": place["geo_lowest_level_value_id"],
                    "geo_code_hierarchy_json": place["geo_code_hierarchy_json"],
                    "foundational_id": m.get("national_id"),
                    "first_name": first, "middle_name": middle, "last_name": last, "given_name": first,
                    "gender": m.get("gender"), "birth_date": parse_date(m.get("birth_date")),
                    "marital_status": m.get("marital_status"), "education_level": m.get("education_level"),
                    "registration_date": today,
                    "is_disabled": (m.get("disability_status") or "NO") != "NO",
                    "is_head": m is head, "relationship_to_the_head": m.get("relationship_to_head"),
                })

        for m in members:
            if m.get("national_id") in registered:
                continue
            seq = number(m["individual_id"])
            farm = farms.get(m["individual_id"]) or {}
            facts = farm.get("farmer") or {}
            first, middle, last = names[m["individual_id"]]
            farmer_id = record_id("farmer", m["individual_id"])
            functional = "FR-" + seq
            place = geo.location(m["geo_pcode"])
            contact = phone(m, facts.get("phone_type") or "PRIMARY")
            rows["g2p_register_farmers"].append({
                **common(farmer_id, functional, household_id, words(first, last),
                         words(functional, m.get("national_id"), first, middle, last, m.get("gender"),
                               m.get("birth_date"), place["names"].get("kebele")), now),
                **address(m),
                "geo_lowest_level_value_id": place["geo_lowest_level_value_id"],
                "geo_code_hierarchy_json": place["geo_code_hierarchy_json"],
                "region_name": place["names"].get("region"), "zone_name": place["names"].get("zone"),
                "woreda_name": place["names"].get("woreda"), "kebele_name": place["names"].get("kebele"),
                "foundational_id": m.get("national_id"), "has_national_id": bool(m.get("national_id")),
                "identity_document_type": facts.get("identity_document_type"),
                "first_name": first, "middle_name": middle, "last_name": last, "given_name": first,
                "gender": m.get("gender"), "birth_date": parse_date(m.get("birth_date")),
                "estimated_age": age_on(m, today),
                "marital_status": m.get("marital_status"), "education_level": m.get("education_level"),
                "disabled": (m.get("disability_status") or "NO") != "NO",
                "phone_numbers": [{"type": contact["phone_type"].lower(), "number": contact["phone_e164"],
                                   "is_primary": True}] if contact else None,
                "has_personal_phone": contact is not None,
                "registration_date": today,
                "is_household_head": created and m is head,
                "language_spoken": facts.get("language_spoken"), "local_language": facts.get("local_language"),
                "is_psnp_user": facts.get("is_psnp_user"), "is_farmer": facts.get("is_farmer"),
                "farming_type": facts.get("farming_type"), "income_sources": facts.get("income_sources"),
            })
            if contact:
                rows["g2p_register_farmer_phones"].append({
                    **common(record_id("phone", m["individual_id"]), "PHONE-" + seq, farmer_id,
                             words(contact["phone_type"], contact["phone_number"]),
                             words(contact["phone_type"], contact["phone_number"], contact["phone_e164"]), now),
                    **contact,
                })
            lands = {}
            for n, land in enumerate(farm.get("lands") or [], 1):
                land_id = record_id("land", f"{m['individual_id']}:{land['land_ref']}")
                lands[land["land_ref"]] = land_id
                facts_land = {k: v for k, v in land.items() if k != "land_ref"}
                name = words(land.get("land_size"), land.get("unit"), land.get("current_land_use"))
                rows["g2p_register_lands"].append({
                    **common(land_id, f"LAND-{seq}-{n}", farmer_id, name,
                             words(land.get("land_ownership_type"), name, land.get("farming_type")), now),
                    **address(m),
                    "geo_lowest_level_value_id": place["geo_lowest_level_value_id"],
                    "geo_code_hierarchy_json": place["geo_code_hierarchy_json"],
                    **facts_land,
                    "area_in_hectare": land.get("land_size") if land.get("unit") == "HECTARE" else None,
                })
            for table, key, prefix, label in (
                ("g2p_register_crops", "crops", "CROP", ("commodity", "season")),
                ("g2p_register_livestocks", "livestock", "LIVESTOCK", ("livestock_type", "breed")),
                ("g2p_register_farm_inputs", "farm_inputs", "FARM-INPUTS", ()),
            ):
                for n, row in enumerate(farm.get(key) or [], 1):
                    if row.get("land_ref") not in lands:
                        raise RuntimeError(f"{m['individual_id']} {key} names land {row.get('land_ref')!r}, "
                                           "which is not among their lands")
                    name = words(*(row.get(k) for k in label)) or f"{prefix} {seq} {n}".replace("-", " ").title()
                    rows[table].append({
                        **common(record_id(key, f"{m['individual_id']}:{n}"), f"{prefix}-{seq}-{n}",
                                 lands[row["land_ref"]], name, name, now),
                        **{k: v for k, v in row.items() if k != "land_ref"},
                    })
            if farm.get("membership"):
                membership = farm["membership"]
                name = membership.get("primary_cooperative_name") or "Membership"
                rows["g2p_register_membership_details"].append({
                    **common(record_id("membership", m["individual_id"]), "MEMBERSHIP-" + seq, farmer_id,
                             name, words(name, membership.get("cooperative_union_name")), now),
                    **membership,
                })
    return rows


def adapt(value):
    return Json(value) if isinstance(value, (dict, list)) else value


def insert(cur, table: str, rows: list[dict]) -> int:
    """Insert rows that are not there yet; how many were new."""
    added = 0
    for row in rows:
        columns = list(row)
        cur.execute(
            f'INSERT INTO "public"."{table}" ({", ".join(chr(34) + c + chr(34) for c in columns)}) '
            f'VALUES ({", ".join(["%s"] * len(columns))}) ON CONFLICT ("internal_record_id") DO NOTHING',
            [adapt(row[c]) for c in columns],
        )
        added += cur.rowcount
    return added


def already_registered(cur) -> tuple[set, dict]:
    """Fayda IDs a farmer holds or awaits approval with; each registered member's household."""
    cur.execute(
        "SELECT foundational_id FROM g2p_register_farmers WHERE foundational_id IS NOT NULL"
        " UNION SELECT f.foundational_id FROM g2p_intake_form_farmers f"
        " JOIN g2p_intake_form_submissions s ON s.submission_id = f.submission_id"
        " WHERE s.draft_status = 'FINAL' AND s.approval_status = 'PENDING' AND f.foundational_id IS NOT NULL"
    )
    registered = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT foundational_id, link_internal_record_id FROM g2p_register_household_members"
                " WHERE foundational_id IS NOT NULL")
    return registered, dict(cur.fetchall())


def enqueue_completion_scores(cur, register: str, record_ids: list[str]) -> int:
    """Queue the completion score of new records, as the registry does for approved ones.

    Own-register and list sections, except those of a CORE_TABLE register (its
    model is not generated, so the worker would fail on it).
    """
    if not record_ids:
        return 0
    cur.execute("SELECT register_id FROM g2p_register_definitions WHERE register_mnemonic = %s", (register,))
    found = cur.fetchone()
    if not found:
        return 0
    register_id = found[0]
    cur.execute(
        "SELECT s.section_id FROM g2p_register_sections s"
        " LEFT JOIN g2p_register_definitions d ON d.register_id = s.section_register_id"
        " WHERE s.register_id = %s AND (s.section_register_id = s.register_id OR s.is_list)"
        " AND d.register_purpose IS DISTINCT FROM 'CORE_TABLE'",
        (register_id,),
    )
    sections = [r[0] for r in cur.fetchall()]
    queued = 0
    for rid in record_ids:
        for sid in sections:
            cur.execute(
                "INSERT INTO g2p_completion_score_computation_queue (queue_id, register_id, internal_record_id,"
                " section_id, change_request_id, submission_id, compute_status, compute_number_of_attempts)"
                " VALUES (%s, %s, %s, %s, NULL, NULL, 'PENDING', 0) ON CONFLICT (queue_id) DO NOTHING",
                (str(uuid.uuid5(_QUEUE, f"{register_id}:{rid}:{sid}")), register_id, rid, sid),
            )
            queued += cur.rowcount
    return queued


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def main() -> None:
    mds = mds_client.MdsClient.from_env(required=True)
    people = mds.sample_individuals()
    households = mds.sample_households()
    if not people:
        log("Master Data holds no sample people (load the country pack's samples on commons-services): "
            "nothing to load.")
        return
    farms_file = OPENG2P_DATA_DIR / "packs" / PACK / "samples" / "farms.json"
    farms = {f["individual_id"]: f for f in json.loads(farms_file.read_text(encoding="utf-8"))}
    log(f"{len(people)} sample people in {len(households)} households from Master Data; "
        f"farm facts for {len(farms)} of them from {farms_file}")

    conn = psycopg2.connect(host=env("PGHOST"), port=os.environ.get("PGPORT", "5432"), dbname=env("PGDATABASE"),
                            user=env("PGUSER"), password=env("PGPASSWORD"))
    try:
        with conn, conn.cursor() as cur:
            registered, member_households = already_registered(cur)
            rows = plan(people, households, farms, Geography(mds.geo_chain), registered, member_households,
                        datetime.now(timezone.utc).replace(tzinfo=None))
            for table, table_rows in rows.items():
                log(f"  {table}: {insert(cur, table, table_rows)} new of {len(table_rows)}")
            for register, table in (("Farmer", "g2p_register_farmers"), ("Household", "g2p_register_households")):
                queued = enqueue_completion_scores(cur, register, [r["internal_record_id"] for r in rows[table]])
                log(f"  completion scores queued for {register}: {queued}")
    finally:
        conn.close()
    log("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[load-sample-data] FAILED: {exc}", file=sys.stderr)
        raise
