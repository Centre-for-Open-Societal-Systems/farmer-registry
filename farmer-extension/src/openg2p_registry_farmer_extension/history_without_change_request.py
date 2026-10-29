"""Let record history return rows that have no change request.

Approving an intake writes register history with a submission_id and no
change_request_id (the column is nullable), but the platform's response schema
RecordHistoryData declares ``change_request_id: str``. Every tab with such a
row failed with "Input should be a valid string" (SYS-ERR-001). Making the
field optional, as submission_id already is, lets get_record_history return
them; the stored data is unchanged.
"""
import logging
from typing import Optional

_logger = logging.getLogger("oan-history-without-change-request")


def install() -> bool:
    """Idempotent: RecordHistoryData.change_request_id becomes Optional[str]."""
    try:
        from openg2p_registry_core.schemas import register_payload, register_response
    except ImportError:
        return False
    field = register_payload.RecordHistoryData.model_fields["change_request_id"]
    if field.annotation == Optional[str]:
        return True
    field.annotation = Optional[str]
    field.default = None
    register_payload.RecordHistoryData.model_rebuild(force=True)
    # Containers embed the item schema when built, so rebuild them too.
    for model in (
        register_payload.RecordHistoryListData,
        register_response.RecordHistoryDataResponseBody,
        register_response.RecordHistoryDataResponse,
    ):
        model.model_rebuild(force=True)
    _logger.info("Record history accepts rows without a change request")
    return True
