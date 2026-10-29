#!/usr/bin/env python3
"""Load the Farmer Registry's sample data (db-seed, LOAD_SAMPLE_DATA=true).

Every sample person is registered the way an officer registers a farmer, and
approved the way every register change is approved:

- one Farmer intake per person on the farmer form, saved section by section
  through the staff API, with a placeholder identity document, then finalized;
- the approval request's stage 1 is approved as INTAKE_SEED_APPROVER_1 and its
  stage 2 as INTAKE_SEED_APPROVER_2, through the staff API's AWE proxy;
- the registry's workers ingest the approved intake into the register.

A household is entered on its head's intake (household information and every
member); the other members' intakes pick that household in the household lookup
once the head's intake is in the register.

The data:
- the sample people and households are Master Data's, read through its API
  (/samples, with the MDS_* client-credentials settings), never its database;
- the registry's own facts about them (grandfather's name, lands, crops,
  livestock, farm inputs, cooperative membership) are the ETH-OAN pack's
  samples/farms.json, in the openg2p-data checkout this image carries.

Staff accounts sign in as in the staff portal (staff IAM, then the Keycloak
login form, then IAM's callback), with the sample users' password the chart
passes (global.aweApproverUserPassword). The loader never uses the password
grant and never changes Keycloak.

Idempotent: a person whose Fayda ID a farmer already holds is skipped; a
finalized intake still waiting for approval is approved rather than entered
again; a household one of whose members is already a farmer is reused.
"""

from __future__ import annotations

import html
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mds_client  # noqa: E402  (the registry platform's Master Data client)

FORM = "farmer_ingestion_intake"
INTAKE_ARTIFACT = "registry.intake_form"
IDENTITY_DOCUMENT = "identity_document_1"
PACK = os.environ.get("SAMPLE_PACK", "ETH-OAN")
OPENG2P_DATA_DIR = Path(os.environ.get("OPENG2P_DATA_DIR", "/openg2p-data"))
COUNTRY_CODE = {"ETH": "ET"}
DIAL_CODE = {"ET": "+251"}
HOUSEHOLD_SECTIONS = ("household_information", "household_household_household_member_section_02")
# Sections of the farmer form, in the order the staff portal saves them.
FARMER_SECTIONS = (
    "farmer_household_lookup", "farmer_identity", "farmer_name", "farmer_personal_details", "farmer_phones",
    "farmer_socio_economic_health", *HOUSEHOLD_SECTIONS, "farmer_location", "farmer_lands",
    "farmer_crops_intake", "farmer_farm_inputs_intake", "farmer_livestock_intake", "farmer_membership",
    "farmer_documents",
)
SAMPLE_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 120]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 58>>stream\nBT /F1 14 Tf 20 60 Td (Sample identity document) Tj ET\nendstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def log(message: str) -> None:
    print(f"[load-sample-data] {message}", flush=True)


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
    """A record's location fields for a P-code, from Master Data's geography."""

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
            }
        return self._cache[pcode]


def local_phone(person: dict) -> str | None:
    """+251941923320 -> 0941923320, the way an officer types it."""
    e164 = person.get("phone")
    if not e164:
        return None
    dial = DIAL_CODE.get(COUNTRY_CODE.get(person.get("country") or "ETH", "ET"), "")
    return "0" + e164[len(dial):] if dial and e164.startswith(dial) else e164.lstrip("+")


def without(row: dict, *keys) -> dict:
    return {k: v for k, v in row.items() if k not in keys}


def household_sections(household_id: str, members: list[dict], head: dict, names: dict, today: date,
                       new_id) -> dict[str, list[dict]]:
    """The household information and members, as entered on the head's intake."""
    ages = [age_on(m, today) for m in members]
    return {
        "household_information": [{
            "internal_record_id": household_id,
            "size_of_group": len(members),
            "number_of_children": sum(a is not None and a <= 17 for a in ages),
            "number_of_elderly_members": sum(a is not None and a >= 60 for a in ages),
            "number_of_male_members": sum(m.get("gender") == "MALE" for m in members),
            "number_of_female_members": sum(m.get("gender") == "FEMALE" for m in members),
            "other_land_owner": False, "other_farmer_in_household": len(members) > 1,
            "father_included": False, "mother_included": False,
        }],
        # The Fayda ID lets the household count a member who is also a farmer once.
        "household_household_household_member_section_02": [{
            "internal_record_id": new_id(), "link_internal_record_id": household_id,
            "foundational_id": m.get("national_id"),
            "first_name": names[m["individual_id"]][0], "middle_name": names[m["individual_id"]][1],
            "last_name": names[m["individual_id"]][2],
            "birth_date": m.get("birth_date"), "gender": m.get("gender"), "is_head": m is head,
            **({} if m is head else {"relationship_to_the_head": m.get("relationship_to_head")}),
        } for m in members],
    }


def farm_sections(person: dict, farm: dict, farmer_id: str, new_id) -> dict[str, list[dict]]:
    """The person's lands, the crops, livestock and farm inputs on them, and their membership."""
    lands, sections = {}, {"farmer_lands": []}
    for land in farm.get("lands") or []:
        lands[land["land_ref"]] = new_id()
        sections["farmer_lands"].append({
            "internal_record_id": lands[land["land_ref"]], "link_internal_record_id": farmer_id,
            **without(land, "land_ref"),
            **({"area_in_hectare": land.get("land_size")} if land.get("unit") == "HECTARE" else {}),
        })
    for section, key in (("farmer_crops_intake", "crops"), ("farmer_farm_inputs_intake", "farm_inputs"),
                         ("farmer_livestock_intake", "livestock")):
        sections[section] = []
        for row in farm.get(key) or []:
            if row.get("land_ref") not in lands:
                raise RuntimeError(f"{person['individual_id']} {key} names land {row.get('land_ref')!r}, "
                                   "which is not among their lands")
            sections[section].append({"internal_record_id": new_id(),
                                      "link_internal_record_id": lands[row["land_ref"]],
                                      **without(row, "land_ref")})
    sections["farmer_membership"] = [{"internal_record_id": new_id(), "link_internal_record_id": farmer_id,
                                      **farm["membership"]}] if farm.get("membership") else []
    return sections


def plan(people: list[dict], households: list[dict], farms: dict, geo: Geography, today: date,
         new_id=lambda: str(uuid.uuid4())) -> list[dict]:
    """One intake per sample person, each household's head first. No network, no database.

    A head's intake carries the household (information and members); every
    intake names its pack household, so a member's intake can pick the
    household in the lookup once the head's intake is in the register.
    """
    unknown = sorted(set(farms) - {p["individual_id"] for p in people})
    if unknown:
        raise RuntimeError(f"farms.json names people Master Data does not hold: {unknown}")
    intakes = []
    for household in households:
        members = [p for p in people if p.get("household_id") == household["household_id"]]
        if not members:
            continue
        head = next((m for m in members if m["individual_id"] == household.get("head_individual_id")), None)
        if head is None:
            raise RuntimeError(f"household {household['household_id']} names a head who is not among its people")
        members = [head] + [m for m in members if m is not head]
        facts = {m["individual_id"]: farms.get(m["individual_id"]) or {} for m in members}
        names = {m["individual_id"]: (m.get("given_name"), m.get("fathers_name"),
                                      (facts[m["individual_id"]].get("farmer") or {}).get("grandfathers_name"))
                 for m in members}
        for m in members:
            missing = [label for label, value in zip(("given name", "father's name", "grandfather's name"),
                                                     names[m["individual_id"]]) if not value]
            if missing:
                raise RuntimeError(f"{m['individual_id']} has no {', '.join(missing)}")
        household_id = new_id()
        for m in members:
            farm, farmer = facts[m["individual_id"]], facts[m["individual_id"]].get("farmer") or {}
            first, middle, last = names[m["individual_id"]]
            farmer_id = new_id()
            phone = local_phone(m)
            sections: dict[str, list[dict]] = {
                "farmer_household_lookup": [{"internal_record_id": farmer_id, "is_household_head": m is head}],
                "farmer_identity": [{"internal_record_id": farmer_id, "has_national_id": bool(m.get("national_id")),
                                     "foundational_id": m.get("national_id")}],
                "farmer_name": [{"internal_record_id": farmer_id, "first_name": first, "middle_name": middle,
                                 "last_name": last, "language_spoken": farmer.get("language_spoken")}],
                "farmer_personal_details": [{"internal_record_id": farmer_id, "gender": m.get("gender"),
                                             "birth_date": m.get("birth_date"),
                                             "marital_status": m.get("marital_status"),
                                             "education_level": m.get("education_level")}],
                "farmer_phones": [{"internal_record_id": new_id(), "link_internal_record_id": farmer_id,
                                   "phone_type": farmer.get("phone_type") or "PRIMARY", "phone_number": phone,
                                   "country_code": COUNTRY_CODE.get(m.get("country") or "ETH", "ET"),
                                   "is_primary": True}] if phone else [],
                "farmer_socio_economic_health": [{
                    "internal_record_id": farmer_id, "disabled": (m.get("disability_status") or "NO") != "NO",
                    "income_sources": farmer.get("income_sources"), "is_psnp_user": farmer.get("is_psnp_user"),
                    "is_farmer": farmer.get("is_farmer"), "farming_type": farmer.get("farming_type"),
                }],
                "farmer_location": [{
                    "internal_record_id": farmer_id, "latitude": m.get("latitude"), "longitude": m.get("longitude"),
                    "address_line_1": words(*(m.get("address_parts") or {}).values()) or None,
                    "local_language": farmer.get("local_language"), **geo.location(m["geo_pcode"]),
                }],
                **(household_sections(household_id, members, head, names, today, new_id) if m is head else {}),
                **farm_sections(m, farm, farmer_id, new_id),
                "farmer_documents": [{"internal_record_id": farmer_id,
                                      "identity_document_type": farmer.get("identity_document_type")}],
            }
            intakes.append({
                "individual_id": m["individual_id"], "name": words(first, middle, last),
                "foundational_id": m.get("national_id"), "household": household["household_id"],
                "is_head": m is head, "farmer_id": farmer_id, "household_id": household_id if m is head else None,
                "sections": {s: sections[s] for s in FARMER_SECTIONS if sections.get(s)},
            })
    return intakes


class StaffSession:
    """One staff user signed in like the staff portal: IAM, the Keycloak login form, IAM's callback."""

    def __init__(self, iam_url: str, api_url: str, username: str, password: str):
        self.iam_url, self.api_url = iam_url.rstrip("/"), api_url.rstrip("/")
        self.username, self._password = username, password
        self._token = None
        self.sign_in()

    @staticmethod
    def _open(opener, request) -> tuple[int, object, bytes]:
        """Status, headers (looked up case-insensitively) and body, without following redirects."""
        try:
            with opener.open(request, timeout=60) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def sign_in(self) -> None:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)
        status, _, body = self._open(opener, urllib.request.Request(
            f"{self.iam_url}/auth/start_authentication_transaction?id=1&redirect_uri=/en", data=b"", method="POST"))
        if status != 200:
            raise RuntimeError(f"staff IAM did not start a sign-in for {self.username} ({status})")
        status, _, body = self._open(opener, urllib.request.Request(json.loads(body)["redirectUrl"] + "&prompt=login"))
        form = re.search(r'<form[^>]+id="kc-form-login"[^>]+action="([^"]+)"', body.decode("utf-8", "replace"))
        if status != 200 or not form:
            raise RuntimeError(f"no Keycloak login form for {self.username} ({status})")
        login = urllib.parse.urlencode({"username": self.username, "password": self._password, "credentialId": ""})
        status, headers, body = self._open(opener, urllib.request.Request(
            html.unescape(form.group(1)), data=login.encode(), method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"}))
        callback = headers.get("Location") or ""
        if not callback.startswith(f"{self.iam_url}/auth/callback"):
            said = " ".join(re.findall(r'kc-feedback-text[^>]*>([^<]+)', body.decode("utf-8", "replace")))
            raise RuntimeError(f"Keycloak refused the sign-in of {self.username} ({status}): {said.strip()[:200]}")
        status, _, _ = self._open(opener, urllib.request.Request(callback))
        token = next((c.value for c in jar if c.name == "X-Access-Token"), None)
        if status not in (302, 303, 307) or not token:
            raise RuntimeError(f"staff IAM issued no session for {self.username} ({status})")
        self._token = token
        log(f"signed in as {self.username}")

    def _send(self, path: str, data: bytes, content_type: str) -> tuple[int, dict]:
        for attempt in (1, 2):
            csrf = uuid.uuid4().hex
            request = urllib.request.Request(f"{self.api_url}{path}", data=data, method="POST", headers={
                "Authorization": f"Bearer {self._token}", "X-CSRF-Token": csrf, "Cookie": f"X-CSRF-Token={csrf}",
                "Content-Type": content_type})
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    status, body = response.status, response.read()
            except urllib.error.HTTPError as exc:
                status, body = exc.code, exc.read()
            try:
                reply = json.loads(body or b"{}")
            except ValueError:
                reply = {}
            code = str((reply.get("response_header") or {}).get("response_error_code") or "")
            if attempt == 1 and (status == 401 or code.endswith("401")):
                self.sign_in()  # the session ended during a long run
                continue
            return status, reply
        return status, reply

    def post(self, path: str, payload: dict) -> dict:
        envelope = {
            "request_header": {"sender_app_mnemonic": "farmer-db-seed", "sender_app_url": "http://db-seed",
                               "request_id": str(uuid.uuid4()),
                               "request_timestamp": datetime.now(timezone.utc).isoformat()},
            "request_body": {"request_payload": payload, "pagination_request": {"current_page": 1, "page_size": 100}},
        }
        status, reply = self._send(path, json.dumps(envelope).encode(), "application/json")
        header = reply.get("response_header") or {}
        if status != 200 or header.get("response_status") != "SUCCESS":
            raise RuntimeError(f"{path} as {self.username}: {status} {header.get('response_error_code')} "
                               f"{header.get('response_error_message')}")
        return (reply.get("response_body") or {}).get("response_payload") or {}

    def upload_identity_document(self, name: str) -> list[dict]:
        boundary = uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="documents"; filename="{name}.pdf"\r\n'
                "Content-Type: application/pdf\r\n\r\n").encode() + SAMPLE_PDF + f"\r\n--{boundary}--\r\n".encode()
        status, reply = self._send("/documents/upload_documents", body, f"multipart/form-data; boundary={boundary}")
        documents = ((reply.get("response_body") or {}).get("response_payload") or {}).get("documents") or []
        if status != 200 or not documents:
            header = reply.get("response_header") or {}
            raise RuntimeError(f"identity document upload failed ({status}): {header.get('response_error_message')}")
        return [{"document_id": documents[0]["document_id"], "label": IDENTITY_DOCUMENT}]


class Registry:
    """The registry database: the form's metadata, who is registered, what was ingested. Reads only."""

    def __init__(self):
        self.conn = psycopg2.connect(host=env("PGHOST"), port=os.environ.get("PGPORT", "5432"),
                                     dbname=env("PGDATABASE"), user=env("PGUSER"), password=env("PGPASSWORD"))
        self.conn.autocommit = True

    def rows(self, sql: str, params=()) -> list[tuple]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def form(self) -> tuple[str, str, dict[str, str]]:
        """The farmer form's id, its register, and the register of each of its sections."""
        found = self.rows(
            "SELECT f.form_id, f.register_id, s.section_id, s.section_register_id"
            " FROM g2p_intake_form_definitions f"
            " JOIN g2p_intake_form_ui_tabs t ON t.form_id = f.form_id"
            " JOIN g2p_intake_form_ui_tab_sections ts ON ts.tab_id = t.tab_id"
            " JOIN g2p_register_sections s ON s.section_id = ts.section_id"
            " WHERE f.form_mnemonic = %s", (FORM,))
        if not found:
            raise RuntimeError(f"form {FORM} is not in the registry metadata")
        sections = {section: str(register) for _, _, section, register in found}
        missing = [s for s in FARMER_SECTIONS if s not in sections]
        if missing:
            raise RuntimeError(f"form {FORM} has no section {', '.join(missing)}")
        return str(found[0][0]), str(found[0][1]), sections

    def farmers(self) -> dict[str, str]:
        """Each farmer's Fayda ID, with their household."""
        return {fid: str(link) for fid, link in self.rows(
            "SELECT foundational_id, link_internal_record_id FROM g2p_register_farmers"
            " WHERE foundational_id IS NOT NULL AND record_status = 'ACTIVE'")}

    def awaiting_approval(self) -> dict[str, tuple[str, str]]:
        """Finalized farmer intakes waiting for approval: Fayda ID -> (submission, farmer record)."""
        return {fid: (str(sid), str(rid)) for fid, sid, rid in self.rows(
            "SELECT f.foundational_id, s.submission_id, f.internal_record_id FROM g2p_intake_form_farmers f"
            " JOIN g2p_intake_form_submissions s ON s.submission_id = f.submission_id"
            " WHERE s.draft_status = 'FINAL' AND s.approval_status = 'PENDING' AND f.foundational_id IS NOT NULL")}

    def approval_status(self, submission_id: str) -> str | None:
        found = self.rows("SELECT approval_status FROM g2p_intake_form_submissions WHERE submission_id = %s",
                          (submission_id,))
        return found[0][0] if found else None

    def wait_for(self, table: str, record_id: str, timeout: int) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.rows(f'SELECT 1 FROM "public"."{table}" WHERE internal_record_id = %s', (record_id,)):
                return
            time.sleep(3)
        stuck = self.rows(
            "SELECT register_ingest_process_status, register_ingest_process_attempts,"
            " left(coalesce(register_ingest_process_last_error_code, ''), 300) FROM g2p_intake_form_submissions"
            " WHERE approval_status = 'APPROVED' AND register_ingest_process_status <> 'PROCESSED'"
            " ORDER BY approved_at DESC LIMIT 1")
        raise RuntimeError(f"{table} {record_id} was not ingested within {timeout}s"
                           + (f" (latest unprocessed intake: {stuck[0]})" if stuck else ""))


class Loader:
    def __init__(self, registry: Registry, submitter: StaffSession, approvers: list[StaffSession],
                 approve_timeout: int, ingest_timeout: int):
        self.registry, self.submitter, self.approvers = registry, submitter, approvers
        self.approve_timeout, self.ingest_timeout = approve_timeout, ingest_timeout
        self.form_id, self.register_id, self.section_registers = registry.form()

    def submit(self, intake: dict, household_id: str | None) -> str:
        submission_id = None
        for section, rows in intake["sections"].items():
            if section == "farmer_household_lookup" and household_id:
                rows = [{**rows[0], "link_internal_record_id": household_id}]
            documents = self.submitter.upload_identity_document(intake["individual_id"]) \
                if section == "farmer_documents" else []
            saved = self.submitter.post("/intake-form-data/save_intake_form_submission", {
                "submission_id": submission_id, "section_id": section, "section_payload": rows,
                "section_register_id": self.section_registers[section], "form_id": self.form_id,
                "register_id": self.register_id, "created_by": self.submitter.username, "documents": documents,
            })
            submission_id = submission_id or saved.get("submission_id")
            if not submission_id:
                raise RuntimeError(f"saving {section} for {intake['individual_id']} returned no submission")
        self.submitter.post("/intake-form-data/finalize_intake_form_submission", {
            "submission_id": submission_id, "register_id": self.register_id, "form_id": self.form_id})
        return submission_id

    def approve(self, submission_id: str) -> None:
        """Stage 1 as the first approver, then stage 2 as the second, each once its task opens."""
        deadline = time.time() + self.approve_timeout
        for stage, approver in enumerate(self.approvers, 1):
            while True:
                if self.registry.approval_status(submission_id) == "APPROVED":
                    return
                tasks = approver.post("/awe/list_my_tasks", {"status": "open", "artifact_type": INTAKE_ARTIFACT,
                                                             "page": 1, "page_size": 100})
                task = next((t for t in (tasks.get("data") or {}).get("items") or []
                             if t.get("artifact_id") == submission_id and int(t.get("stage_order") or 0) == stage),
                            None)
                if task:
                    break
                if time.time() > deadline:
                    raise RuntimeError(f"no stage {stage} task for {approver.username} on intake {submission_id} "
                                       f"within {self.approve_timeout}s")
                time.sleep(3)
            approver.post("/awe/claim_task", {"task_id": task["id"]})
            approver.post("/awe/submit_task_decision", {
                "task_id": task["id"], "action": "approve", "comment": "Sample data (db-seed)",
                "artifact_id": submission_id, "artifact_type": INTAKE_ARTIFACT, "current_stage": stage})
            log(f"    stage {stage} approved as {approver.username}")
        while self.registry.approval_status(submission_id) != "APPROVED":
            if time.time() > deadline:
                raise RuntimeError(f"intake {submission_id} is not approved after both stages")
            time.sleep(3)

    def run(self, intakes: list[dict]) -> dict:
        farmers, awaiting = self.registry.farmers(), self.registry.awaiting_approval()
        households = {}  # pack household id -> its household in the register
        for intake in intakes:
            if intake["foundational_id"] in farmers:
                households.setdefault(intake["household"], farmers[intake["foundational_id"]])
        done = {"registered": 0, "resumed": 0, "skipped": 0}
        for intake in intakes:
            who, fid = f"{intake['individual_id']} {intake['name']}", intake["foundational_id"]
            if fid in farmers:
                done["skipped"] += 1
                log(f"  {who}: already a farmer")
                continue
            if fid in awaiting:
                submission_id, farmer_id = awaiting[fid]
                log(f"  {who}: intake {submission_id} waits for approval; approving it")
                self.approve(submission_id)
                self.registry.wait_for("g2p_register_farmers", farmer_id, self.ingest_timeout)
                farmers = self.registry.farmers()
                households.setdefault(intake["household"], farmers.get(fid))
                done["resumed"] += 1
                continue
            household_id = households.get(intake["household"])
            if household_id is None and not intake["is_head"]:
                raise RuntimeError(f"{who}: household {intake['household']} is not in the register, so this "
                                   "member cannot be picked into it")
            if household_id is not None and intake["is_head"]:
                # A member registered first: the head joins that household instead of entering it again.
                intake = {**intake, "sections": without(intake["sections"], *HOUSEHOLD_SECTIONS)}
            submission_id = self.submit(intake, household_id)
            log(f"  {who}: intake {submission_id} submitted")
            self.approve(submission_id)
            self.registry.wait_for("g2p_register_farmers", intake["farmer_id"], self.ingest_timeout)
            if household_id is None:
                self.registry.wait_for("g2p_register_households", intake["household_id"], self.ingest_timeout)
                households[intake["household"]] = household_id = intake["household_id"]
            farmers[fid] = household_id
            done["registered"] += 1
            log(f"  {who}: in the register")
        return done


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, "").strip() or default
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def main() -> None:
    mds = mds_client.MdsClient.from_env(required=True)
    people, households = mds.sample_individuals(), mds.sample_households()
    if not people:
        log("Master Data holds no sample people (load the country pack's samples on commons-services): "
            "nothing to load.")
        return
    farms_file = OPENG2P_DATA_DIR / "packs" / PACK / "samples" / "farms.json"
    farms = {f["individual_id"]: f for f in json.loads(farms_file.read_text(encoding="utf-8"))}
    log(f"{len(people)} sample people in {len(households)} households from Master Data; "
        f"farm facts for {len(farms)} of them from {farms_file}")
    intakes = plan(people, households, farms, Geography(mds.geo_chain), date.today())

    iam, api, password = env("STAFF_IAM_URL"), env("STAFF_API_URL"), env("INTAKE_SEED_PASSWORD")
    sessions: dict[str, StaffSession] = {}

    def session(user: str) -> StaffSession:
        if user not in sessions:
            sessions[user] = StaffSession(iam, api, user, password)
        return sessions[user]

    registry = Registry()
    try:
        loader = Loader(
            registry, session(env("INTAKE_SEED_SUBMIT_USER", "alex.carter")),
            [session(env("INTAKE_SEED_APPROVER_1", "alex.carter")),
             session(env("INTAKE_SEED_APPROVER_2", "nina.patel"))],
            int(env("INTAKE_SEED_APPROVE_TIMEOUT", "300")), int(env("INTAKE_SEED_INGEST_TIMEOUT", "300")))
        done = loader.run(intakes)
    finally:
        registry.conn.close()
    log(f"Done: {done['registered']} farmers registered, {done['resumed']} waiting intakes approved, "
        f"{done['skipped']} already farmers.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[load-sample-data] FAILED: {exc}", file=sys.stderr)
        raise
