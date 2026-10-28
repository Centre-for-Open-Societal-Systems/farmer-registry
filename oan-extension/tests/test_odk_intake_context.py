"""Uncommitted intake lands are visible only in their own submission scope."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openg2p_registry_core.errors import G2PRegistryException

from oan_farmer_registry_extension.register_domain.services import intake_context


def test_normal_domain_validation_keeps_its_original_parent_link():
    records = [{"link_internal_record_id": "registered-land"}]
    assert asyncio.run(intake_context.validation_records(records, "Crop")) is records


def test_own_uncommitted_land_is_checked_in_the_intake_session_without_mutating_payload():
    records = [{"link_internal_record_id": "new-land", "commodity": "CROP_MAIZE"}]
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(submission_id="submission-1")))
    token = intake_context.current_intake.set((session, "submission-1"))
    try:
        normalized = asyncio.run(intake_context.validation_records(records, "Crop"))
        assert normalized == [{"commodity": "CROP_MAIZE"}]
        assert records[0]["link_internal_record_id"] == "new-land"
        assert session.get.call_args.args[1] == ("submission-1", "new-land")
    finally:
        intake_context.current_intake.reset(token)


def test_another_intakes_land_cannot_satisfy_current_intake_validation():
    session = SimpleNamespace(get=AsyncMock(side_effect=[SimpleNamespace(submission_id="another-intake"), None]))
    token = intake_context.current_intake.set((session, "submission-1"))
    try:
        with pytest.raises(G2PRegistryException, match="select a land on this intake"):
            asyncio.run(intake_context.validation_records([{"link_internal_record_id": "foreign-land"}], "Crop"))
    finally:
        intake_context.current_intake.reset(token)
