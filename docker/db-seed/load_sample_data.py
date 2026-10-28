#!/usr/bin/env python3
"""Register the country pack's sample people as Farmers, through intake and approval.

The people and their households are Master Data's sample records
(g2p_sample_individuals / g2p_sample_households), which Master Data loads from
the country pack's samples/. Their farm facts (grandfather's name, lands with
crops, livestock and farm inputs, cooperative membership) are the same pack's
samples/farms.json, baked into this image from openg2p-data. Nothing is
invented here: a value the pack does not give is left empty.

Each household is entered on its head's farmer form, with its members, the
way a new household is registered in the staff portal: on approval the
household gets that farmer as its head. Every other person of the household
is then a farmer picked into it through the household lookup. Every
submission is finalized and approved through AWE like any other, and Celery
ingests it. The HTTP, AWE and
ingest helpers are OpenG2P's own sample loader's (openg2p_sample_loader.py,
unchanged). Forms, sections and registers are looked up by mnemonic in the
registry's metadata, and a record is split over the sections whose widgets
write its fields.

Staff accounts: the loader logs in as the chart's sample approvers with the
password the chart passes. Only when Keycloak refuses that login (keycloak-init
creates them with a temporary password, and the release client without the
password grant) does it prepare them as OpenG2P's own sample loader does:
direct access grants on the release client, the same password made permanent.

Idempotent per person: a person whose Fayda ID a farmer already holds (or
awaits approval with), or a household whose head is already a registered
member, is skipped, so a re-run continues where it stopped and never
duplicates.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parent))
import openg2p_sample_loader as base

FARMS_FILE = Path(os.environ.get("OAN_FARM_SAMPLES", "/seed/samples/farms.json"))
FARMER_FORM = "farmer_ingestion_intake"
IDENTITY_DOCUMENT_LABEL = "identity_document_1"
COUNTRY_CODE = {"ETH": "ET"}


def log(msg: str) -> None:
    print(f"[oan-samples] {msg}", flush=True)


# ── Sources ──────────────────────────────────────────────────────────────────

def master_data_samples() -> tuple[list[dict], list[dict], dict]:
    """Sample people, their households and the geography they sit on."""
    conn = base._md_connect()
    if conn is None:
        raise RuntimeError("MD_PG* is not set: the sample people are read from Master Data")
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM g2p_sample_individuals ORDER BY individual_id")
            people = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT * FROM g2p_sample_households ORDER BY household_id")
            households = [dict(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT v.level_value_id, v.level_value_mnemonic, v.parent_level_value_id,"
                " l.level_id, l.level_mnemonic"
                " FROM g2p_geo_level_values v JOIN g2p_geo_levels l ON l.level_id = v.level_id"
            )
            geo = {r["level_value_id"]: dict(r) for r in cur.fetchall()}
    finally:
        conn.close()
    return people, households, geo


def geo_location(geo: dict, pcode: str) -> dict:
    """The geo-hierarchy widget's value for a P-code, as the staff portal saves it."""
    chain, cur = [], pcode
    while cur in geo and len(chain) < 10:
        unit = geo[cur]
        chain.append({
            "level": unit["level_mnemonic"], "level_id": unit["level_id"],
            "level_mnemonic": unit["level_mnemonic"], "level_value_id": cur,
            "level_value_mnemonic": unit["level_value_mnemonic"],
        })
        cur = unit["parent_level_value_id"]
    if not chain:
        raise RuntimeError(f"{pcode} is not a unit of Master Data's published geography")
    chain.reverse()
    return {
        "geo_lowest_level_value_id": pcode,
        "geo_code_hierarchy_json": {"hierarchy": chain, "lowest_level_value_id": pcode},
    }


def section_fields(schema, register_id: str):
    """The fields a section's widgets write on its register."""
    if isinstance(schema, dict):
        path = schema.get("widget-data-path")
        for p in path.values() if isinstance(path, dict) else [path]:
            if isinstance(p, str) and p.startswith(register_id + "."):
                yield p.split(".")[-1]
        for value in schema.values():
            yield from section_fields(value, register_id)
    elif isinstance(schema, list):
        for value in schema:
            yield from section_fields(value, register_id)


class Form:
    """A form's sections in order, with the register and fields of each."""

    def __init__(self, rows: list[dict], mnemonic: str):
        if not rows:
            raise RuntimeError(f"form {mnemonic} is not in the registry metadata")
        self.form_id, self.register_id = rows[0]["form_id"], rows[0]["register_id"]
        self.sections = [
            {**r, "fields": set(section_fields(r["section_ui_schema"], r["section_register_id"]))}
            for r in rows
        ]

    @classmethod
    def load(cls, conn, mnemonic: str) -> Form:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT f.form_id, f.register_id, s.section_id, s.section_register_id,"
                " s.section_ui_schema, d.register_mnemonic"
                " FROM g2p_intake_form_definitions f"
                " JOIN g2p_intake_form_ui_tabs t ON t.form_id = f.form_id"
                " JOIN g2p_intake_form_ui_tab_sections ts ON ts.tab_id = t.tab_id"
                " JOIN g2p_register_sections s ON s.section_id = ts.section_id"
                " JOIN g2p_register_definitions d ON d.register_id = s.section_register_id"
                " WHERE f.form_mnemonic = %s ORDER BY t.tab_order, ts.section_order",
                (mnemonic,),
            )
            return cls([dict(r) for r in cur.fetchall()], mnemonic)

    def sections_of(self, register: str, fields=None) -> list[dict]:
        """The sections of a register, or only those writing one of `fields`."""
        found = [s for s in self.sections if s["register_mnemonic"] == register]
        if fields is not None:
            found = [s for s in found if s["fields"] & set(fields)]
        if not found:
            raise RuntimeError(f"no section of register {register} on this form writes {sorted(fields or [])}")
        return found


# ── Records ──────────────────────────────────────────────────────────────────

def full_name(person: dict, farm: dict) -> tuple[str, str, str]:
    """An Ethiopian name: the person's, the father's and the grandfather's."""
    return (person["given_name"], person.get("fathers_name") or "",
            (farm.get("farmer") or {}).get("grandfathers_name") or "")


def iso(value) -> str | None:
    return value.isoformat() if isinstance(value, date) else (str(value) if value else None)


def age(person: dict, today: date | None = None) -> int:
    born = person.get("birth_date")
    if not isinstance(born, date):
        return int(person.get("age") or 0)
    today = today or date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def member_record(person: dict) -> dict:
    first, middle, last = person["name"]
    return {
        "first_name": first, "middle_name": middle, "last_name": last,
        "gender": person["gender"], "birth_date": iso(person.get("birth_date")),
        "is_head": person["relationship_to_head"] == "SELF",
        "relationship_to_the_head": person["relationship_to_head"],
        "foundational_id": person.get("national_id"),
    }


def household_record(household: dict, members: list[dict], head: dict, geo: dict) -> dict:
    ages = [age(m) for m in members]
    return {
        "household_head": " ".join(n for n in head["name"] if n),
        "size_of_group": len(members),
        "number_of_male_members": sum(m["gender"] == "MALE" for m in members),
        "number_of_female_members": sum(m["gender"] == "FEMALE" for m in members),
        "number_of_children": sum(a < 18 for a in ages),
        "number_of_elderly_members": sum(a >= 60 for a in ages),
        "other_land_owner": False,
        "country_code": COUNTRY_CODE.get(household.get("country") or "ETH", "ET"),
        "address_line_1": base._address_line(household.get("address_parts")) or None,
        "latitude": household.get("latitude"), "longitude": household.get("longitude"),
        **geo_location(geo, household["geo_pcode"]),
    }


def farmer_record(person: dict, household_id: str, geo: dict, is_head: bool | None = None) -> dict:
    facts = {k: v for k, v in (person["farm"].get("farmer") or {}).items()
             if k not in ("grandfathers_name", "phone_type")}
    first, middle, last = person["name"]
    nid = person.get("national_id")
    return {
        "link_internal_record_id": household_id,
        "is_household_head": person["relationship_to_head"] == "SELF" if is_head is None else is_head,
        "has_national_id": bool(nid), "foundational_id": nid,
        "first_name": first, "middle_name": middle, "last_name": last,
        "gender": person["gender"], "birth_date": iso(person.get("birth_date")),
        "marital_status": person.get("marital_status"),
        "education_level": person.get("education_level"),
        "disabled": (person.get("disability_status") or "NO") != "NO",
        "country_code": COUNTRY_CODE.get(person.get("country") or "ETH", "ET"),
        "address_line_1": base._address_line(person.get("address_parts")) or None,
        "latitude": person.get("latitude"), "longitude": person.get("longitude"),
        **geo_location(geo, person["geo_pcode"]),
        **facts,
    }


def phone_rows(person: dict) -> list[dict]:
    if not person.get("phone"):
        return []
    kind = (person["farm"].get("farmer") or {}).get("phone_type") or "PRIMARY"
    return [{"phone_type": kind, "phone_number": person["phone"], "country_code": "ET", "is_primary": True}]


def same_name(a, b) -> bool:
    return " ".join(str(a or "").split()).casefold() == " ".join(str(b or "").split()).casefold()


def without(record: dict, *keys) -> dict:
    return {k: v for k, v in record.items() if k not in keys}


def plan(people: list[dict], households: list[dict], farms: dict) -> list[tuple[dict, list[dict], dict]]:
    """(household, its members, its head) with each person's name and farm facts attached."""
    for person in people:
        person["farm"] = farms.get(person["individual_id"], {})
        person["name"] = full_name(person, person["farm"])
    result = []
    for household in households:
        members = [p for p in people if p["household_id"] == household["household_id"]]
        head = next((m for m in members if m["individual_id"] == household["head_individual_id"]), None)
        if head is None:
            raise RuntimeError(f"household {household['household_id']} names a head who is not among its people")
        result.append((household, members, head))
    return result


# ── Submission ───────────────────────────────────────────────────────────────

class Seeder:
    def __init__(self, client, clients, awe_conn, approve_timeout: int, ingest_timeout: int):
        self.client, self.clients, self.awe_conn = client, clients, awe_conn
        self.approve_timeout, self.ingest_timeout = approve_timeout, ingest_timeout
        conn = base.registry_connect()
        try:
            self.farmer_form = Form.load(conn, FARMER_FORM)
        finally:
            conn.close()

    def save(self, form: Form, section: dict, submission_id, records: list[dict], documents=None) -> dict:
        result = self.client.post("/intake-form-data/save_intake_form_submission", {
            "submission_id": submission_id,
            "section_id": section["section_id"],
            "section_payload": records,
            "section_register_id": section["section_register_id"],
            "form_id": form.form_id,
            "register_id": form.register_id,
            "created_by": self.client.username,
            "documents": documents or [],
        })
        if not result or not result.get("submission_id"):
            raise RuntimeError(f"saving {section['section_id']} returned no submission: {result}")
        return result

    def save_record(self, form: Form, register: str, record: dict, submission_id) -> tuple[str, str]:
        """One record, saved over every section of its register that writes its fields."""
        record_id = None
        for section in form.sections_of(register, record):
            row = {k: v for k, v in record.items() if k in section["fields"] or k == "link_internal_record_id"}
            if record_id:
                row["internal_record_id"] = record_id
            result = self.save(form, section, submission_id, [row])
            submission_id = submission_id or result["submission_id"]
            record_id = record_id or base.section_record_id(result, section["section_register_id"])
        return submission_id, record_id

    def save_rows(self, form: Form, register: str, rows: list[dict], submission_id) -> list[str]:
        if not rows:
            return []
        section = form.sections_of(register)[0]
        ids = base.section_record_ids(self.save(form, section, submission_id, rows), section["section_register_id"])
        if len(ids) != len(rows):
            raise RuntimeError(f"{register}: saved {len(rows)} rows, got {len(ids)} ids back")
        return ids

    def approve(self, form: Form, submission_id: str) -> None:
        base.finalize(self.client, submission_id, form.register_id, form.form_id)
        base.approve_intake(self.clients, self.awe_conn, submission_id, self.approve_timeout)

    def upload_identity_document(self) -> list[dict]:
        """A placeholder scan for the identity document the farmer form requires."""
        boundary = uuid.uuid4().hex
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="documents"; filename="sample-id.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode() + SAMPLE_PDF + f"\r\n--{boundary}--\r\n".encode()
        headers = {k: v for k, v in self.client.headers.items() if k != "Content-Type"}
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        req = urllib_request.Request(f"{self.client.base_url}/documents/upload_documents",
                                     data=body, headers=headers, method="POST")
        try:
            with urllib_request.urlopen(req, timeout=60, context=base._ssl_ctx()) as resp:
                reply = json.loads(resp.read() or b"{}")
        except urllib_error.HTTPError as exc:
            raise RuntimeError(f"identity document upload failed ({exc.code}): {exc.read()[:300]!r}") from exc
        payload = ((reply.get("response_body") or {}).get("response_payload") or {})
        documents = payload.get("documents") or []
        if not documents:
            raise RuntimeError(f"identity document upload returned no document: {reply}")
        return [{"document_id": documents[0]["document_id"], "label": IDENTITY_DOCUMENT_LABEL}]

    def submit_farmer(self, person: dict, geo: dict, household_id: str | None = None,
                      is_head: bool | None = None, new_household: tuple | None = None) -> tuple[str, str]:
        """One farmer, picked into a registered household, or entered with a new
        one (household, members, head) whose head the farmer is."""
        form, farm, submission_id = self.farmer_form, person["farm"], None
        if new_household:
            household, members, head = new_household
            submission_id, household_id = self.save_record(
                form, "Household", household_record(household, members, head, geo), None)
            self.save_rows(form, "HouseholdMember",
                           [{**member_record(m), "link_internal_record_id": household_id} for m in members],
                           submission_id)
            is_head = True
        record = farmer_record(person, household_id, geo, is_head)
        submission_id, farmer_id = self.save_record(
            form, "Farmer", without(record, "identity_document_type"), submission_id)
        self.save_rows(form, "FarmerPhone",
                       [{**r, "link_internal_record_id": farmer_id} for r in phone_rows(person)], submission_id)
        lands = farm.get("lands") or []
        land_ids = dict(zip(
            [land["land_ref"] for land in lands],
            self.save_rows(form, "Land", [{**without(land, "land_ref"), "link_internal_record_id": farmer_id}
                                          for land in lands], submission_id),
        ))
        for register, key in (("Crop", "crops"), ("Livestock", "livestock"), ("FarmInputs", "farm_inputs")):
            self.save_rows(form, register, [
                {**without(row, "land_ref"), "link_internal_record_id": land_ids[row["land_ref"]]}
                for row in farm.get(key) or []
            ], submission_id)
        if farm.get("membership"):
            self.save_record(form, "MembershipDetails",
                             {**farm["membership"], "link_internal_record_id": farmer_id}, submission_id)
        documents = form.sections_of("Farmer", ["identity_document_type"])[0]
        self.save(form, documents, submission_id, [{
            "internal_record_id": farmer_id, "link_internal_record_id": household_id,
            "identity_document_type": record.get("identity_document_type"),
        }], self.upload_identity_document())
        self.approve(form, submission_id)
        base.wait_register_row("g2p_register_farmers", farmer_id, self.ingest_timeout)
        if new_household:
            base.wait_register_row("g2p_register_households", household_id, self.ingest_timeout)
        return farmer_id, household_id


def already_registered(conn) -> tuple[set, dict, dict]:
    """Fayda IDs a farmer already holds or awaits approval with, the household
    of each registered member's Fayda ID, and each household's head."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT foundational_id FROM g2p_register_farmers WHERE foundational_id IS NOT NULL"
            " UNION SELECT f.foundational_id FROM g2p_intake_form_farmers f"
            " JOIN g2p_intake_form_submissions s ON s.submission_id = f.submission_id"
            " WHERE s.draft_status = 'FINAL' AND s.approval_status = 'PENDING'"
            " AND f.foundational_id IS NOT NULL"
        )
        farmers = {r[0] for r in cur.fetchall()}
        cur.execute(
            "SELECT foundational_id, link_internal_record_id FROM g2p_register_household_members"
            " WHERE foundational_id IS NOT NULL"
        )
        members = dict(cur.fetchall())
        cur.execute("SELECT internal_record_id, household_head FROM g2p_register_households")
        heads = {str(k): v for k, v in cur.fetchall()}
    return farmers, members, heads


def staff_clients() -> tuple[object, dict]:
    token_url = base.env("STAFF_TOKEN_URL", required=True)
    client_id = base.env("STAFF_CLIENT_ID", required=True)
    client_secret = base.env("STAFF_CLIENT_SECRET")
    password = base.env("INTAKE_SEED_PASSWORD", required=True)
    staff_api = base.env("STAFF_API_URL", required=True)
    submit_user = base.env("INTAKE_SEED_SUBMIT_USER", "alex.carter")
    users = dict.fromkeys([submit_user, base.env("INTAKE_SEED_APPROVER_1", "alex.carter"),
                           base.env("INTAKE_SEED_APPROVER_2", "nina.patel")])
    def token(u):
        return base.fetch_token(token_url, client_id, u, password, client_secret)

    try:
        for user in users:
            token(user)
    except RuntimeError as exc:
        # keycloak-init creates the demo approvers with a temporary password and
        # the release client without the password grant. Make them usable the
        # way OpenG2P's own sample loader does, only when the login is refused.
        log(f"{exc}; preparing the sample approvers in Keycloak")
        base.keycloak_prepare_users(
            base.env("KEYCLOAK_BASE_URL", required=True), base.env("KEYCLOAK_REALM", required=True),
            base.env("KEYCLOAK_ADMIN_USER", required=True), base.env("KEYCLOAK_ADMIN_PASSWORD", required=True),
            client_id, list(users), password,
        )
    clients = {}
    for user in users:
        clients[user] = base.StaffClient(staff_api, token(user), user, token_provider=lambda u=user: token(u))
        log(f"logged in as {user}")
    return clients[submit_user], clients


def main() -> None:
    people, households, geo = master_data_samples()
    if not people:
        log("Master Data has no sample people (load the country pack with samples): nothing to seed.")
        return
    farms = {f["individual_id"]: f for f in json.loads(FARMS_FILE.read_text(encoding="utf-8"))} \
        if FARMS_FILE.exists() else {}
    log(f"{len(people)} people in {len(households)} households from Master Data, "
        f"{len(farms)} farm records from {FARMS_FILE}")
    households_plan = plan(people, households, farms)

    conn = base.registry_connect()
    try:
        farmers_done, member_households, heads = already_registered(conn)
    finally:
        conn.close()

    client, clients = staff_clients()
    awe_conn = psycopg2.connect(
        host=base.env("AWE_PGHOST", required=True), port=base.env("AWE_PGPORT", "5432"),
        dbname=base.env("AWE_PGDATABASE", "awe"), user=base.env("AWE_PGUSER"),
        password=base.env("AWE_PGPASSWORD"),
    )
    seeder = Seeder(client, clients, awe_conn, base.env_int("INTAKE_SEED_APPROVE_TIMEOUT", 300),
                    base.env_int("INTAKE_SEED_INGEST_TIMEOUT", 300))
    created = {"households": 0, "farmers": 0}
    try:
        for household, members, head in households_plan:
            household_id = member_households.get(head.get("national_id"))
            for person in [head] + [m for m in members if m is not head]:
                name = " ".join(n for n in person["name"] if n)
                if person.get("national_id") in farmers_done:
                    log(f"  farmer {person['individual_id']}: already registered or awaiting approval")
                    continue
                if household_id is None and person is not head:
                    log(f"  farmer {person['individual_id']}: waits for household {household['household_id']}, "
                        "whose head awaits approval")
                    continue
                if household_id is None:
                    _, household_id = seeder.submit_farmer(person, geo, new_household=(household, members, head))
                    created["households"] += 1
                    log(f"household {household['household_id']}: registered with its head {name}")
                else:
                    # A registered household's head changes only through a change
                    # request; mark the head only where the household names them.
                    is_head = person is head and same_name(heads.get(str(household_id)), name)
                    if person is head and not is_head:
                        log(f"  household {household['household_id']} names no head; {name} joins it as a member")
                    seeder.submit_farmer(person, geo, household_id=household_id, is_head=is_head)
                created["farmers"] += 1
                log(f"  farmer {person['individual_id']} {name}: registered")
    finally:
        awe_conn.close()
    log(f"Done: {created['farmers']} farmers and {created['households']} households registered.")


# One page reading "Sample identity document": the farmer form requires a file.
SAMPLE_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 120]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 58>>stream\nBT /F1 14 Tf 20 60 Td (Sample identity document) Tj ET\nendstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[oan-samples] FAILED: {exc}", file=sys.stderr)
        raise
