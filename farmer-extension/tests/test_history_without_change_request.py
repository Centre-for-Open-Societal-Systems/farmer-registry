"""Record history returns history rows that have no change request."""

import pytest

pytest.importorskip("openg2p_registry_core")
from openg2p_registry_core.schemas.register_payload import RecordHistoryData, RecordHistoryListData
from openg2p_registry_core.schemas.register_response import RecordHistoryDataResponseBody

from openg2p_registry_farmer_extension import history_without_change_request


def _row(**extra):
    return {"history_record_id": "h1", "internal_record_id": "r1", "tab_id": "t", "section_id": "s", **extra}


def test_intake_history_row_without_change_request_is_returned():
    assert history_without_change_request.install()
    row = RecordHistoryData(**_row(change_request_id=None, submission_id="sub-1", farmer_id="FR-1"))
    listing = RecordHistoryListData(register_id="reg", internal_record_id="r1", tab_id="t", history_records=[row])
    body = RecordHistoryDataResponseBody(response_payload=listing).model_dump()
    record = body["response_payload"]["history_records"][0]
    assert record["change_request_id"] is None
    assert record["submission_id"] == "sub-1"
    assert record["farmer_id"] == "FR-1"


def test_change_request_rows_are_unchanged():
    assert history_without_change_request.install()
    assert RecordHistoryData(**_row(change_request_id="cr-1")).change_request_id == "cr-1"


def test_install_is_idempotent():
    assert history_without_change_request.install()
    assert history_without_change_request.install()
