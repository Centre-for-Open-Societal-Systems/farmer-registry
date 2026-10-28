#!/usr/bin/env python3
"""Seed Farmer Registry sample records through the intake-form API.

MDS sample households are submitted and approved first. Their heads
are then submitted as farmers with the live household id. No farm assets or
reference values are invented. Each intake is finalized and approved by
alex.carter (stage 1) and nina.patel (stage 2). Celery ingest writes the
register rows — this script never INSERTs into g2p_register_*.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import psycopg2
import psycopg2.extras

from master_data_samples import load_samples

# ── Register / form / section ids (farmer-extension meta_data) ───────────────
HOUSEHOLD_REGISTER_ID = "9055ab43-c85d-4833-bd00-ca657bb72644"
HOUSEHOLD_FORM_ID = "9055ab43-c85d-4833-bd00-ca657bb72650"
FARMER_REGISTER_ID = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"
FARMER_FORM_ID = "a1a4d25a-1cd4-4356-abac-8782382649"
LAND_REGISTER_ID = "493153d5-07ef-4743-8efd-07f4099772b9"
CROP_REGISTER_ID = "5fa096f8-ffdc-4b0a-ab16-9ca386c23310"
LIVESTOCK_REGISTER_ID = "4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb"
FARM_INPUTS_REGISTER_ID = "18df8370-3e9a-493f-aa27-fc1b9e05629c"
MEMBERSHIP_REGISTER_ID = "495f251c-83a5-4025-a307-1925712c9d0b"
HH_MEMBER_REGISTER_ID = "52979fdd-220c-48dd-8de0-0a434e786427"

HH_INFO_SECTION = "household_household_household_information_section_01"
HH_LOCATION_SECTION = "household_household_location_section_03"
HH_MEMBER_SECTION = "household_household_household_member_section_02"

FARMER_LOOKUP_SECTION = "farmer_household_lookup_section_01"
FARMER_PERSONAL_SECTION = "farmer_farmer_personal_identification_section_01"
FARMER_SOCIO_SECTION = "farmer_farmer_socio_economic_and_health_section_04"
FARMER_LOCATION_SECTION = "farmer_farmer_location_section_03"
FARMER_LAND_SECTION = "farmer_farm_farm_details_section_01"
FARMER_CROP_SECTION = "farmer_crop_crop_details_intake_section_01"
FARMER_INPUT_SECTION = "farmer_farm_input_farm_input_details_intake_section_01"
FARMER_LIVESTOCK_SECTION = "farmer_livestock_livestock_details_intake_section_01"
FARMER_MEMBERSHIP_SECTION = "farmer_membership_membership_details_01"

ARTIFACT_INTAKE = "registry.intake_form"

def log(msg: str) -> None:
    print(f"[load-sample-data] {msg}", flush=True)


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default if default is not None else "")
    if required and not value:
        print(f"[load-sample-data] Missing env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def registry_env(name: str, required: bool = True) -> str:
    """Registry Postgres setting. REGISTRY_PG* wins so AWE seed cannot hijack PG*."""
    value = os.environ.get(f"REGISTRY_{name}") or os.environ.get(name) or ""
    awe_db = os.environ.get("AWE_PGDATABASE") or ""
    if name == "PGDATABASE" and awe_db and value == awe_db:
        print(
            "[load-sample-data] PGDATABASE is the AWE database "
            f"({awe_db}). Set REGISTRY_PGDATABASE to the farmer registry DB.",
            file=sys.stderr,
        )
        sys.exit(1)
    if required and not value:
        print(
            f"[load-sample-data] Missing env var: REGISTRY_{name} or {name}",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


# ── Geo (master-data) ────────────────────────────────────────────────────────

_GEO_BY_ID: dict = {}


def _md_connect():
    host = os.environ.get("MD_PGHOST")
    dbname = os.environ.get("MD_PGDATABASE")
    if not host or not dbname:
        return None
    return psycopg2.connect(
        host=host,
        port=os.environ.get("MD_PGPORT", "5432"),
        dbname=dbname,
        user=os.environ.get("MD_PGUSER", ""),
        password=os.environ.get("MD_PGPASSWORD", ""),
    )


def load_geo_indexes() -> None:
    global _GEO_BY_ID
    conn = _md_connect()
    if conn is None:
        log("MD_PG* not set — geo ids will be empty.")
        return
    try:
        with conn.cursor() as cur:
            cur.execute("select level_id, level_mnemonic from g2p_geo_levels")
            mnemonic = dict(cur.fetchall())
            cur.execute(
                "select level_value_id, level_id, level_value_mnemonic, "
                "parent_level_value_id from g2p_geo_level_values"
            )
            rows = cur.fetchall()
            _GEO_BY_ID = {
                vid: (mnemonic.get(lid, lid), name, parent)
                for vid, lid, name, parent in rows
            }
        log(f"master-data geo: {len(_GEO_BY_ID)} units.")
    finally:
        conn.close()


def hierarchy_from_id(pcode: str) -> dict:
    chain = []
    seen, cur = set(), pcode
    while cur and cur in _GEO_BY_ID and cur not in seen:
        seen.add(cur)
        level, name, parent = _GEO_BY_ID[cur]
        chain.append(
            {
                "level_mnemonic": level,
                "level_value_mnemonic": name,
                "level_value_id": cur,
            }
        )
        cur = parent
    chain.reverse()
    return {"hierarchy": chain}


def geo_for_record(rec: dict) -> tuple[str, dict]:
    pcode = rec.get("geo_pcode")
    if not pcode or pcode not in _GEO_BY_ID:
        raise ValueError(f"Sample geography {pcode!r} is absent from published MDS geography")
    return pcode, hierarchy_from_id(pcode)


def _as_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def person_phones(person: dict) -> list | None:
    if not person.get("phone"):
        return None
    return [{"type": "personal", "number": str(person["phone"]), "is_primary": True}]


def geo_fields(rec: dict) -> dict:
    lowest, hierarchy = geo_for_record(rec)
    return {
        "latitude": _as_float(rec.get("latitude")),
        "longitude": _as_float(rec.get("longitude")),
        "address_line_1": rec.get("address_line_1"),
        "country_code": rec.get("country_code"),
        "geo_lowest_level_value_id": lowest,
        "geo_code_hierarchy_json": hierarchy,
    }


def person_fields(person: dict, *, extra: dict | None = None) -> dict:
    # MDS samples do not contain titles, email, income or occupation. Do not
    # fabricate them (in particular, Mr/Ms are labels, not PREFIX codes).
    payload = {key: person.get(key) for key in (
        "first_name", "middle_name", "last_name", "given_name", "gender",
        "birth_date", "foundational_id", "marital_status", "education_level",
    )}
    payload.update({
        "phone_numbers": person_phones(person),
        "registration_date": date.today().isoformat(),
        **geo_fields(person),
    })
    if extra:
        payload.update(extra)
    return payload


def _ssl_ctx():
    if env_bool("INTAKE_SEED_VERIFY_TLS", True):
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def http_json(
    method: str,
    url: str,
    *,
    data: dict | None = None,
    headers: dict | None = None,
    form: dict | None = None,
    timeout: int = 60,
) -> tuple[int, Any]:
    body = None
    hdrs = dict(headers or {})
    if form is not None:
        body = urllib_parse.urlencode(form).encode()
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif data is not None:
        body = json.dumps(data).encode()
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib_request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib_request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as resp:
            raw = resp.read()
            parsed = json.loads(raw.decode()) if raw else {}
            return resp.status, parsed
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(raw) if raw else {"text": raw}
        except json.JSONDecodeError:
            parsed = {"text": raw[:800]}
        return exc.code, parsed

AUTH_WAIT_SECONDS = env_int("SEED_AUTH_WAIT_SECONDS", 300)


def _error_detail(body) -> str:
    """Best-effort human-readable message out of an API error body."""
    if isinstance(body, dict):
        header = body.get("response_header") or {}
        if isinstance(header, dict) and header.get("response_error_message"):
            return str(header["response_error_message"])
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0] if isinstance(errors[0], dict) else {"message": errors[0]}
            return str(first.get("message") or first)
        for key in ("message", "detail"):
            if body.get(key):
                return str(body[key])
    return str(body)[:200] if body else ""


class StaffClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        username: str,
        token_provider: Callable[[], str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        # Re-login hook: Keycloak access tokens are short-lived (5 min by
        # default) and a full seed of 25+ households runs well past that.
        self._token_provider = token_provider
        csrf = uuid.uuid4().hex
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf,
            "Cookie": f"X-CSRF-Token={csrf}",
        }

    def refresh_token(self) -> bool:
        if self._token_provider is None:
            return False
        self.headers["Authorization"] = f"Bearer {self._token_provider()}"
        log(f"  re-logged in as {self.username} (access token expired)")
        return True

    def post(self, path: str, payload: dict) -> dict:
        envelope = {
            "request_header": {
                "sender_app_mnemonic": "farmer-db-seed",
                "sender_app_url": "http://db-seed",
                "request_id": uuid.uuid4().hex,
                "request_timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "request_body": {"request_payload": payload},
        }
        url = f"{self.base_url}{path}"
        last_err = None
        # A 403 right after a deployment means IAM cannot yet map this user's client
        # roles to permissions: the iam-register job that publishes this registry's
        # roles/permissions catalog has not finished (or ran after db-seed). Retry for
        # AUTH_WAIT_SECONDS instead of the old ~40s, and report the API's own message
        # so the cause is visible in the job log.
        auth_deadline = time.time() + AUTH_WAIT_SECONDS
        attempt = 0
        while True:
            attempt += 1
            status, body = http_json("POST", url, data=envelope, headers=self.headers)
            header = (body or {}).get("response_header") or {}
            err_code = str(header.get("response_error_code", "")) if isinstance(header, dict) else ""
            if (status == 401 or err_code.endswith("401")) and attempt <= 8 and self.refresh_token():
                last_err = f"{path} as {self.username} -> 401 (token refreshed, retrying)"
                continue
            if status == 403 or err_code.endswith("403"):
                detail = _error_detail(body)
                last_err = (
                    f"{path} as {self.username} -> 403 {detail} (retried for "
                    f"{AUTH_WAIT_SECONDS}s: this user's roles resolve to no permissions in "
                    "IAM — check that the iam-register job for this registry completed "
                    "and that the user holds the staff-portal client roles)"
                )
                if time.time() < auth_deadline:
                    if attempt == 1 or attempt % 6 == 0:
                        log(f"  {path} as {self.username} -> 403 {detail}; waiting for IAM permissions…")
                    time.sleep(5)
                    continue
                break
            if attempt > 8:
                break
            if status != 200:
                raise RuntimeError(f"{path} as {self.username} -> {status}: {body}")
            if header.get("response_status") == "ERROR":
                raise RuntimeError(
                    f"{path} as {self.username} ERROR "
                    f"{header.get('response_error_code')}: {header.get('response_error_message')}"
                )
            return ((body or {}).get("response_body") or {}).get("response_payload") or body
        raise RuntimeError(last_err or f"{path} failed")


def fetch_token(token_url: str, client_id: str, username: str, password: str, client_secret: str) -> str:
    form = {
        "grant_type": "password",
        "client_id": client_id,
        "username": username,
        "password": password,
        "scope": "openid",
    }
    if client_secret:
        form["client_secret"] = client_secret
    status, body = http_json("POST", token_url, form=form, timeout=20)
    if status != 200:
        raise RuntimeError(f"password grant failed for '{username}' ({status}): {body}")
    return body["access_token"]


def section_record_id(save_result: dict, section_register_id: str) -> str:
    for payload in save_result.get("section_payloads") or []:
        if payload.get("section_register_id") != section_register_id:
            continue
        records = payload.get("records") or []
        if records:
            rid = records[0].get("internal_record_id")
            if rid:
                return rid
    raise RuntimeError(f"no internal_record_id returned for {section_register_id}")


def section_record_ids(save_result: dict, section_register_id: str) -> list[str]:
    for payload in save_result.get("section_payloads") or []:
        if payload.get("section_register_id") != section_register_id:
            continue
        return [
            r["internal_record_id"]
            for r in (payload.get("records") or [])
            if r.get("internal_record_id")
        ]
    return []


def save_section(
    client: StaffClient,
    *,
    submission_id: str | None,
    section_id: str,
    section_register_id: str,
    form_id: str,
    register_id: str,
    records: list[dict],
) -> dict:
    payload = {
        "submission_id": submission_id,
        "section_id": section_id,
        "section_payload": records,
        "section_register_id": section_register_id,
        "form_id": form_id,
        "register_id": register_id,
        "created_by": client.username,
        "documents": [],
    }
    result = client.post("/intake-form-data/save_intake_form_submission", payload)
    if not result or not result.get("submission_id"):
        raise RuntimeError(f"save {section_id} returned no submission_id: {result}")
    return result


def finalize(client: StaffClient, submission_id: str, register_id: str, form_id: str) -> dict:
    return client.post(
        "/intake-form-data/finalize_intake_form_submission",
        {"submission_id": submission_id, "register_id": register_id, "form_id": form_id},
    )


def open_awe_tasks(awe_conn, artifact_id: str) -> list[dict]:
    with awe_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT t.id AS task_id, t.stage_order, t.assignee
              FROM approval_task t
              JOIN approval_request r ON r.id = t.request_id
             WHERE r.artifact_id = %s
               AND t.status IN ('open', 'claimed')
             ORDER BY t.stage_order
            """,
            (str(artifact_id),),
        )
        return [dict(r) for r in cur.fetchall()]


def approve_intake(
    clients: dict[str, StaffClient],
    awe_conn,
    submission_id: str,
    timeout: int,
) -> None:
    """Walk AWE stages: alex.carter then nina.patel."""
    deadline = time.time() + timeout
    approved_any = False
    while time.time() < deadline:
        registry_conn = registry_connect()
        try:
            status = submission_approval_status(registry_conn, submission_id)
        finally:
            registry_conn.close()
        if status == "APPROVED":
            log(f"  submission {submission_id} approved")
            return
        tasks = open_awe_tasks(awe_conn, submission_id)
        if not tasks:
            if approved_any:
                time.sleep(2)
                continue
            time.sleep(2)
            continue
        for task in tasks:
            assignee = (task.get("assignee") or "").strip()
            client = clients.get(assignee) or clients.get(assignee.split("@")[0])
            if client is None:
                raise RuntimeError(f"No configured seed credential for AWE assignee {assignee!r}")
            client.post(
                "/awe/submit_task_decision",
                {
                    "task_id": str(task["task_id"]),
                    "action": "approve",
                    "comment": f"db-seed intake approve ({client.username})",
                    "artifact_id": str(submission_id),
                    "artifact_type": ARTIFACT_INTAKE,
                    "current_stage": int(task.get("stage_order") or 1),
                },
            )
            log(
                f"  approved AWE task {task['task_id']} "
                f"stage={task.get('stage_order')} as {client.username}"
            )
            approved_any = True
        time.sleep(2)
    raise RuntimeError(
        f"submission {submission_id} was not approved within {timeout}s "
        "(check AWE, alex.carter / nina.patel, and celery ingest)"
    )


def registry_connect():
    return psycopg2.connect(
        host=registry_env("PGHOST"),
        port=os.environ.get("REGISTRY_PGPORT") or os.environ.get("PGPORT", "5432"),
        dbname=registry_env("PGDATABASE"),
        user=registry_env("PGUSER"),
        password=registry_env("PGPASSWORD"),
    )


def submission_approval_status(conn, submission_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "select approval_status from g2p_intake_form_submissions where submission_id = %s",
            (submission_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _ingest_diagnosis() -> str:
    """Why an approved submission has not been ingested, read from the DB.

    Ingest is not done by the API: celery-beat publishes *_beat_producer tasks to the
    DEFAULT celery queue, the worker that runs them enqueues
    intake_form_register_ingest_worker onto registry_worker_queue, and the celery-worker
    performs the insert. attempts=0 with no error means the task never reached a worker,
    which is usually nothing consuming the default queue (the beat pod needs
    `-Q celery` in CELERY_OPTS); an error means the ingest itself failed.
    """
    try:
        conn = registry_connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "select register_ingest_process_status, register_ingest_process_attempts,"
                    " left(coalesce(register_ingest_process_last_error_code,''), 300)"
                    " from g2p_intake_form_submissions"
                    " where approval_status = 'APPROVED'"
                    "   and register_ingest_process_status <> 'PROCESSED'"
                    " order by approved_at desc limit 1"
                )
                row = cur.fetchone()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return f"(could not read ingest status: {exc})"

    if not row:
        return (
            "No approved submission is awaiting ingest, so the row may have been written "
            "just after the timeout; consider raising INTAKE_SEED_INGEST_TIMEOUT."
        )
    status, attempts, error = row[0], row[1] or 0, (row[2] or "").strip()
    if error:
        return f"Ingest ran and failed (status={status}, attempts={attempts}): {error}"
    return (
        f"Ingest never ran (status={status}, attempts={attempts}, no error recorded). "
        "The task did not reach a worker: check that celery-beat's CELERY_OPTS names the "
        "queue it consumes (worker --beat -Q celery ...) — without -Q its worker starts "
        "but consumes nothing, so producer tasks pile up on the default 'celery' queue "
        "and never reach registry_worker_queue. Also check celery-worker is running and "
        "that both pods use the same Redis."
    )


def wait_register_row(table: str, internal_id: str, timeout: int) -> None:
    deadline = time.time() + timeout
    sql = f'select 1 from "public"."{table}" where internal_record_id = %s'
    while time.time() < deadline:
        conn = registry_connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (internal_id,))
                if cur.fetchone():
                    return
        finally:
            conn.close()
        time.sleep(2)
    raise RuntimeError(
        f"{table} row {internal_id} not ingested within {timeout}s. "
        f"{_ingest_diagnosis()}"
    )


def wait_linked_rows(
    table: str,
    link_id: str | None,
    minimum: int,
    timeout: int,
    via_land_of: str | None = None,
) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        conn = registry_connect()
        try:
            with conn.cursor() as cur:
                if via_land_of:
                    cur.execute(
                        f"""
                        select count(*) from "public"."{table}" c
                         join "public"."g2p_register_lands" l
                           on l.internal_record_id = c.link_internal_record_id
                        where l.link_internal_record_id = %s
                        """,
                        (via_land_of,),
                    )
                else:
                    cur.execute(
                        f'select count(*) from "public"."{table}" where link_internal_record_id = %s',
                        (link_id,),
                    )
                if cur.fetchone()[0] >= minimum:
                    return
        finally:
            conn.close()
        time.sleep(2)
    raise RuntimeError(
        f"{table} did not reach {minimum} ingested row(s) within {timeout}s"
    )


def already_seeded(households: list[dict]) -> bool:
    """Do not mistake unrelated records for samples or duplicate a partial seed.

    Completed source identities are a no-op. Partial/in-flight source identities
    require native intake recovery before retry; this seed never force-replays.
    """
    identities = [hh["head"]["foundational_id"] for hh in households]
    conn = registry_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT foundational_id FROM g2p_register_farmers WHERE foundational_id = ANY(%s)", (identities,))
            registered = [row[0] for row in cur.fetchall()]
            if len(registered) == len(identities) and set(registered) == set(identities):
                return True
            cur.execute("SELECT count(*) FROM g2p_intake_form_farmers WHERE foundational_id = ANY(%s)", (identities,))
            pending = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM g2p_intake_form_households WHERE household_head = ANY(%s)",
                        ([hh["head"]["full_name"] for hh in households],))
            household_intakes = cur.fetchone()[0]
            if registered or pending or household_intakes:
                raise RuntimeError("Partial or existing MDS sample identities found; recover their native intakes before retrying (no force replay)")
            return False
    finally:
        conn.close()


def household_payload(hh: dict) -> dict:
    members = hh["members"]
    males = sum(1 for m in members if (m.get("gender") or "").upper() == "MALE")
    females = sum(1 for m in members if (m.get("gender") or "").upper() == "FEMALE")
    children = sum(1 for m in members if (m.get("estimated_age") or 0) < 18)
    elderly = sum(1 for m in members if (m.get("estimated_age") or 0) >= 60)
    size = len(members)
    return {
        "household_head": hh["head"]["full_name"],
        "size_of_group": size,
        "number_of_children": children,
        "number_of_elderly_members": elderly,
        "number_of_male_members": males,
        "number_of_female_members": females,
        **geo_fields(hh),
    }


def member_payload(member: dict, household_intake_id: str, *, is_head: bool = False) -> dict:
    return {
        **person_fields(member),
        "is_disabled": member["disability_status"] == "YES",
        "is_head": is_head,
        "relationship_to_the_head": member["relationship_to_head"],
        "link_internal_record_id": household_intake_id,
    }


def submit_household(client: StaffClient, hh: dict) -> tuple[str, str]:
    info = household_payload(hh)
    saved = save_section(
        client,
        submission_id=None,
        section_id=HH_INFO_SECTION,
        section_register_id=HOUSEHOLD_REGISTER_ID,
        form_id=HOUSEHOLD_FORM_ID,
        register_id=HOUSEHOLD_REGISTER_ID,
        records=[info],
    )
    submission_id = saved["submission_id"]
    hh_id = section_record_id(saved, HOUSEHOLD_REGISTER_ID)
    loc = {**info, "internal_record_id": hh_id}
    save_section(
        client,
        submission_id=submission_id,
        section_id=HH_LOCATION_SECTION,
        section_register_id=HOUSEHOLD_REGISTER_ID,
        form_id=HOUSEHOLD_FORM_ID,
        register_id=HOUSEHOLD_REGISTER_ID,
        records=[loc],
    )
    head_id = hh["head"].get("internal_record_id")
    members = [
        member_payload(
            m,
            hh_id,
            is_head=m.get("internal_record_id") == head_id,
        )
        for m in hh["members"]
    ]
    save_section(
        client,
        submission_id=submission_id,
        section_id=HH_MEMBER_SECTION,
        section_register_id=HH_MEMBER_REGISTER_ID,
        form_id=HOUSEHOLD_FORM_ID,
        register_id=HOUSEHOLD_REGISTER_ID,
        records=members,
    )
    finalize(client, submission_id, HOUSEHOLD_REGISTER_ID, HOUSEHOLD_FORM_ID)
    return submission_id, hh_id


def submit_farmer(
    client: StaffClient, hh: dict, household_id: str, index: int
) -> tuple[str, str]:
    farmer = hh["head"]
    extra = {"disabled": farmer["disability_status"] == "YES", "has_personal_phone": bool(farmer.get("phone"))}
    extra["estimated_age"] = farmer["estimated_age"]
    extra["national_id_masked"] = f"XXXX{farmer['foundational_id'][-4:]}"
    personal = {
        **person_fields(farmer, extra=extra),
        "link_internal_record_id": household_id,
    }
    saved = save_section(
        client,
        submission_id=None,
        section_id=FARMER_PERSONAL_SECTION,
        section_register_id=FARMER_REGISTER_ID,
        form_id=FARMER_FORM_ID,
        register_id=FARMER_REGISTER_ID,
        records=[personal],
    )
    submission_id = saved["submission_id"]
    farmer_id = section_record_id(saved, FARMER_REGISTER_ID)
    linked = {**personal, "internal_record_id": farmer_id, "link_internal_record_id": household_id}
    save_section(
        client,
        submission_id=submission_id,
        section_id=FARMER_LOOKUP_SECTION,
        section_register_id=FARMER_REGISTER_ID,
        form_id=FARMER_FORM_ID,
        register_id=FARMER_REGISTER_ID,
        records=[linked],
    )
    save_section(
        client,
        submission_id=submission_id,
        section_id=FARMER_SOCIO_SECTION,
        section_register_id=FARMER_REGISTER_ID,
        form_id=FARMER_FORM_ID,
        register_id=FARMER_REGISTER_ID,
        records=[linked],
    )
    save_section(
        client,
        submission_id=submission_id,
        section_id=FARMER_LOCATION_SECTION,
        section_register_id=FARMER_REGISTER_ID,
        form_id=FARMER_FORM_ID,
        register_id=FARMER_REGISTER_ID,
        records=[linked],
    )

    finalize(client, submission_id, FARMER_REGISTER_ID, FARMER_FORM_ID)
    return submission_id, farmer_id


def main() -> None:
    log("Starting intake-form sample seed…")
    staff_api = env("STAFF_API_URL", "http://127.0.0.1:8001")
    token_url = env(
        "STAFF_TOKEN_URL",
        env("KEYCLOAK_ISSUER_URL", "") + "/protocol/openid-connect/token"
        if env("KEYCLOAK_ISSUER_URL")
        else "",
    )
    if not token_url:
        print(
            "[load-sample-data] Set STAFF_TOKEN_URL or KEYCLOAK_ISSUER_URL "
            "(Keycloak password-grant token endpoint).",
            file=sys.stderr,
        )
        sys.exit(1)
    client_id = env("STAFF_CLIENT_ID", required=True)
    client_secret = env("STAFF_CLIENT_SECRET")
    password = env("INTAKE_SEED_PASSWORD", env("KEYCLOAK_AWE_APPROVER_PASSWORD"), required=True)
    submit_user = env("INTAKE_SEED_SUBMIT_USER", "alex.carter")
    approver1 = env("INTAKE_SEED_APPROVER_1", "alex.carter")
    approver2 = env("INTAKE_SEED_APPROVER_2", "nina.patel")
    ingest_timeout = env_int("INTAKE_SEED_INGEST_TIMEOUT", 180)
    approve_timeout = env_int("INTAKE_SEED_APPROVE_TIMEOUT", 180)
    max_hh = env_int("INTAKE_SEED_MAX_HOUSEHOLDS", 25)

    load_geo_indexes()
    _, households = load_samples(_md_connect, _GEO_BY_ID)
    if max_hh < 1:
        raise ValueError("INTAKE_SEED_MAX_HOUSEHOLDS must be positive")
    households = households[:max_hh]
    if already_seeded(households):
        log("All requested MDS household heads already exist; no records changed.")
        return
    # Account provisioning belongs to IAM/Keycloak, never to a data seed.
    users = list(dict.fromkeys([submit_user, approver1, approver2]))

    clients: dict[str, StaffClient] = {}
    for username in users:
        token = fetch_token(token_url, client_id, username, password, client_secret)
        clients[username] = StaffClient(
            staff_api,
            token,
            username,
            token_provider=lambda u=username: fetch_token(
                token_url, client_id, u, password, client_secret
            ),
        )
        log(f"logged in as {username}")
    submitter = clients[submit_user]

    awe_conn = psycopg2.connect(
        host=env("AWE_PGHOST", env("PGHOST", required=True)),
        port=os.environ.get("AWE_PGPORT", os.environ.get("PGPORT", "5432")),
        dbname=env("AWE_PGDATABASE", "awe"),
        user=env("AWE_PGUSER", env("PGUSER", "")),
        password=env("AWE_PGPASSWORD", env("PGPASSWORD", "")),
    )

    try:
        for index, hh in enumerate(households):
            log(f"household {index + 1}/{len(households)}: {hh['head']['full_name']}")
            hh_sub, hh_id = submit_household(submitter, hh)
            approve_intake(clients, awe_conn, hh_sub, approve_timeout)
            wait_register_row("g2p_register_households", hh_id, ingest_timeout)
            wait_linked_rows("g2p_register_household_members", hh_id, len(hh["members"]), ingest_timeout)
            log(f"  household ingested id={hh_id}")

            log(f"farmer {index + 1}/{len(households)}: {hh['head']['full_name']} -> household {hh_id}")
            fr_sub, fr_id = submit_farmer(submitter, hh, hh_id, index)
            approve_intake(clients, awe_conn, fr_sub, approve_timeout)
            wait_register_row("g2p_register_farmers", fr_id, ingest_timeout)
            log(f"  farmer ingested id={fr_id}")
    finally:
        awe_conn.close()
    log("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[load-sample-data] FAILED: {exc}", file=sys.stderr)
        raise
