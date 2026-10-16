"""Approve only the synthetic draft produced by browser_acceptance.cjs."""
import os

from sanity import db
from tests.test_e2e_intake import approve, payload


def test_browser_draft_attachments_survive_approval(cfg, staff_client):
    submission_id = os.environ["SANITY_OVERLAY_SUBMISSION_ID"]
    farmers = db.query(cfg.registry_dsn, """
        SELECT internal_record_id, first_name, record_image_document_id,
               geo_lowest_level_value_id FROM g2p_intake_form_farmers
        WHERE submission_id=%s
        """, (submission_id,))
    assert len(farmers) == 1 and farmers[0]["first_name"] == "Overlayacceptance"
    farmer = farmers[0]
    assert farmer["record_image_document_id"]
    assert farmer["geo_lowest_level_value_id"] == "kebele-ET010103201001"
    lands = db.query(cfg.registry_dsn, """
        SELECT internal_record_id, land_id, certificate_storage_id, certificate_provided
        FROM g2p_intake_form_lands WHERE submission_id=%s ORDER BY land_id
        """, (submission_id,))
    assert len(lands) == 2
    assert lands[0]["land_id"] == "OVERLAY-A"
    assert not lands[0]["certificate_storage_id"] and lands[0]["certificate_provided"] is False
    assert lands[1]["land_id"] == "OVERLAY-B"
    assert lands[1]["certificate_storage_id"] and lands[1]["certificate_provided"] is True
    payload(staff_client.post("/intake-form-data/finalize_intake_form_submission", {"submission_id": submission_id}))
    approve(cfg, staff_client, submission_id)
    live = db.query(cfg.registry_dsn, """
        SELECT internal_record_id, first_name, record_image_document_id,
               geo_lowest_level_value_id FROM g2p_register_farmers WHERE internal_record_id=%s
        """, (farmer["internal_record_id"],))
    assert live == farmers
    for land in lands:
        live_land = db.query(cfg.registry_dsn, """
            SELECT internal_record_id, land_id, certificate_storage_id, certificate_provided
            FROM g2p_register_lands WHERE internal_record_id=%s
            """, (land["internal_record_id"],))
        assert live_land == [land]
