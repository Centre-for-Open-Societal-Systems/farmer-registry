"""Native outgestion accepts Python-valued hierarchy extras after approvals."""

import asyncio
import importlib.util
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

pytest.importorskip("openg2p_registry_core")
from openg2p_registry_core.models import OutgoingRawDataPayload

_path = (
    Path(__file__).parents[1]
    / "src/oan_farmer_registry_extension/register_domain/services/outgest_json.py"
)
_spec = importlib.util.spec_from_file_location("oan_outgest_json_test", _path)
module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(module)


def test_native_payload_decimal_reproduction_and_json_boundary(monkeypatch):
    record = {
        "area": Decimal("1.234567890123456789"),
        "children": [
            {
                "dob": date(2000, 1, 2),
                "at": datetime(2026, 1, 2, tzinfo=UTC),
                "id": UUID("00000000-0000-0000-0000-000000000001"),
            }
        ],
    }
    with pytest.raises(TypeError, match="Decimal"):
        OutgoingRawDataPayload(payload_id="before", raw_data_json=record)
    native = AsyncMock(return_value=record)
    monkeypatch.setattr(
        module.G2PRegisterHierarchicalService, "enrich_record_hierarchy", native
    )
    result = asyncio.run(
        module.JsonSafeHierarchyService().enrich_record_hierarchy(None, None, None)
    )
    payload = OutgoingRawDataPayload(payload_id="after", raw_data_json=result)
    assert json.loads(payload.raw_data_text) == result
    assert result["area"] == "1.234567890123456789"
    assert result["children"][0]["dob"] == "2000-01-02"
    assert result["children"][0]["at"] == "2026-01-02T00:00:00Z"
    assert result["children"][0]["id"] == "00000000-0000-0000-0000-000000000001"
    assert record["area"] == Decimal("1.234567890123456789")


def test_installer_and_native_fanout_injection(monkeypatch):
    service = module.install_outgest_json()
    assert module.G2PRegisterChangeRequestService.get_component() is service
    assert module.install_outgest_json() is service
    base = module.G2PRegisterChangeRequestService
    assert (
        service.approve_change_request_from_awe_webhook.__func__
        is base.approve_change_request_from_awe_webhook
    )
    service._get_register_class_and_schema = AsyncMock(
        return_value=("definition", "class", None)
    )
    service._get_existing_record = AsyncMock(return_value="row")
    fanout = AsyncMock()
    monkeypatch.setattr(module, "fanout_outgest_rows", fanout)
    cr = SimpleNamespace(
        register_id="register",
        internal_record_id="record",
        change_request_id="cr",
        created_by="creator",
        created_at="created",
        approved_by="reviewer",
        approved_at="approved",
        source_partner_id=None,
    )
    asyncio.run(service._fanout_outgest_for_change_request(cr, "session"))
    assert isinstance(
        fanout.call_args.kwargs["hierarchical_service"], module.JsonSafeHierarchyService
    )
    assert fanout.call_args.kwargs["approved_by"] == "reviewer"
    assert fanout.call_args.kwargs["change_request_id"] == "cr"
    service._get_existing_record = AsyncMock(return_value=None)
    fanout.reset_mock()
    asyncio.run(service._fanout_outgest_for_change_request(cr, "session"))
    fanout.assert_not_called()


def test_intake_ingest_fanout_uses_json_hierarchy(monkeypatch):
    """The worker's ingest task gets a fanout that swaps in the JSON-safe hierarchy."""
    import sys
    from types import ModuleType

    name = "oan_fake_ingest_worker"
    fake = ModuleType(name)
    fake.fanout_outgest_rows = module.fanout_outgest_rows
    monkeypatch.setitem(sys.modules, name, fake)
    module.install_outgest_json()
    assert module.install_intake_outgest_json(name) is fake
    assert fake.fanout_outgest_rows is module.fanout_outgest_rows_json
    assert module.install_intake_outgest_json(name) is fake

    native = AsyncMock()
    monkeypatch.setattr(module, "fanout_outgest_rows", native)
    asyncio.run(
        fake.fanout_outgest_rows(
            "definition",
            "row",
            "session",
            intake_form_submission_id="submission",
            changed_by="system",
            changed_at="now",
            hierarchical_service=module.G2PRegisterHierarchicalService(),
        )
    )
    assert isinstance(
        native.call_args.kwargs["hierarchical_service"], module.JsonSafeHierarchyService
    )
    assert native.call_args.kwargs["intake_form_submission_id"] == "submission"
    assert module.install_intake_outgest_json("oan_missing_worker_module") is None
