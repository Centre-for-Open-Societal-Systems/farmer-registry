"""Staff intake and an explicitly supplied ODK submission through real AWE.

Creates labelled local test records. ODK submission creation/polling occurs
outside this suite; SANITY_ODK_INSTANCE_ID identifies exactly that submission.
"""
import os
import time

import pytest
from sanity import db

FORM_ID = "a1a4d25a-1cd4-4356-abac-8782382649"


def payload(response):
    assert response.get("response_header", {}).get("response_status") != "ERROR", response
    return response["response_body"]["response_payload"]


def approve(cfg, staff_client, submission_id):
    deadline = time.monotonic() + cfg.awe_settle_timeout
    decisions = 0
    while time.monotonic() < deadline:
        row = db.query(cfg.registry_dsn,
            "SELECT approval_status, register_ingest_process_status FROM g2p_intake_form_submissions WHERE submission_id=%s",
            (submission_id,))[0]
        if row["approval_status"] == "APPROVED" and row["register_ingest_process_status"] == "PROCESSED":
            assert decisions > 0, "No AWE task was exercised"
            return
        tasks = db.query(cfg.awe_dsn, """
            SELECT t.id, t.stage_order FROM approval_task t
            JOIN approval_request r ON r.id=t.request_id
            WHERE r.artifact_id=%s AND t.status IN ('open','claimed') ORDER BY t.stage_order
            """, (submission_id,))
        # any-n stages may skip siblings immediately after one decision.
        # Read the task set again before deciding the next task.
        for task in tasks[:1]:
            payload(staff_client.submit_task_decision({
                "task_id": str(task["id"]), "action": "approve", "comment": "Local Gen2 intake acceptance test",
                "artifact_id": submission_id, "artifact_type": "registry.intake_form",
                "current_stage": task["stage_order"],
            }))
            decisions += 1
        time.sleep(2)
    pytest.fail(f"Intake {submission_id} did not complete approval/ingestion: {row}")


@pytest.mark.e2e
def test_staff_intake_save_readback_approval(cfg, staff_client):
    record = {"edit_action": "ADD", "is_household_head": False,
              "first_name": "Genintaketest", "last_name": "Local", "gender": "MALE",
              "birth_date": "1990-01-01", "estimated_age": 36,
              "latitude": "9.03", "longitude": 38.7469, "altitude": "1800"}
    common = {"section_register_id": cfg.farmer_register_id, "form_id": FORM_ID,
              "register_id": cfg.farmer_register_id, "section_payload": [record]}
    saved = payload(staff_client.post("/intake-form-data/save_intake_form_submission", {
        **common, "section_id": "farmer_farmer_personal_identification_section_01",
    }))
    submission_id = saved["submission_id"]
    payload(staff_client.post("/intake-form-data/save_intake_form_submission", {
        **common, "submission_id": submission_id, "section_id": "farmer_household_lookup_section_01",
    }))
    readback = payload(staff_client.post("/intake-form-data/get_intake_form_submission", {"submission_id": submission_id}))
    records = [r for s in readback["section_payloads"] for r in s["records"]]
    assert any(r.get("first_name") == "Genintaketest" and r.get("is_household_head") is False for r in records)
    assert any(r.get("latitude") == 9.03 and r.get("longitude") == 38.7469 for r in records)
    payload(staff_client.post("/intake-form-data/finalize_intake_form_submission", {"submission_id": submission_id}))
    approve(cfg, staff_client, submission_id)
    rows = db.query(cfg.registry_dsn, """
        SELECT r.first_name, r.is_household_head FROM g2p_register_farmers r
        JOIN g2p_intake_form_farmers i USING(internal_record_id) WHERE i.submission_id=%s
        """, (submission_id,))
    assert len(rows) == 1 and rows[0]["first_name"] == "Genintaketest"
    assert rows[0]["is_household_head"] is False
    print(f"Staff intake saved, read back and approved: {submission_id}")


@pytest.mark.e2e
def test_odk_ingestion_attachments_and_approval(cfg, staff_client):
    instance = os.environ.get("SANITY_ODK_INSTANCE_ID")
    if not instance:
        pytest.skip("Set SANITY_ODK_INSTANCE_ID after submitting to local ODK Central")
    deadline = time.monotonic() + 180
    while True:
        rows = db.query(cfg.registry_dsn, """
            SELECT c.ingestion_status, c.ingestion_latest_error_code, c.intake_form_submission_id
            FROM incoming_raw_data r JOIN incoming_classified_data c USING(ingest_id)
            WHERE r.ingest_message_id=%s
            """, ("farmer_profile:" + instance,))
        if rows and rows[0]["ingestion_status"] in ("PROCESSED", "FAILED"):
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(3)
    assert len(rows) == 1, "Expected exactly one ingested message from the connector"
    assert rows[0]["ingestion_status"] == "PROCESSED", rows
    submission_id = rows[0]["intake_form_submission_id"]
    farmer = db.query(cfg.registry_dsn,
        "SELECT internal_record_id,record_image_document_id,geo_lowest_level_value_id,enumerator_name FROM g2p_intake_form_farmers WHERE submission_id=%s",
        (submission_id,))[0]
    assert farmer["record_image_document_id"], "ODK photo was lost"
    assert farmer["geo_lowest_level_value_id"] == "kebele-ET040801101001"
    lands = db.query(cfg.registry_dsn,
        "SELECT certificate_storage_id FROM g2p_intake_form_lands WHERE submission_id=%s", (submission_id,))
    assert lands and all(r["certificate_storage_id"] for r in lands), "ODK land certificate was lost"
    docs = payload(staff_client.post("/documents/get_intake_form_documents", {"submission_id": submission_id}))
    assert farmer["record_image_document_id"] in str(docs)
    assert lands[0]["certificate_storage_id"] in str(docs)
    state = db.query(cfg.registry_dsn,
        "SELECT draft_status,created_by FROM g2p_intake_form_submissions WHERE submission_id=%s", (submission_id,))[0]
    assert state["created_by"] and state["created_by"] != "system"
    assert state["created_by"] == farmer["enumerator_name"]
    if state["draft_status"] == "DRAFT":
        payload(staff_client.post("/intake-form-data/finalize_intake_form_submission", {"submission_id": submission_id}))
    approve(cfg, staff_client, submission_id)
    live = db.query(cfg.registry_dsn,
        "SELECT record_image_document_id,geo_lowest_level_value_id FROM g2p_register_farmers WHERE internal_record_id=%s",
        (farmer["internal_record_id"],))[0]
    assert live["record_image_document_id"] == farmer["record_image_document_id"]
    assert live["geo_lowest_level_value_id"] == farmer["geo_lowest_level_value_id"]
    print(f"ODK intake processed once, attachments retained and approved: {submission_id}")
