import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("handoff", ROOT / "integrations/registry-connector/checkpoint_handoff.py")
handoff = importlib.util.module_from_spec(spec); spec.loader.exec_module(handoff)


def row(value=None, ids=None):
    state = {"_checkpoint": {"mode": "timestamp", "value": value, "boundary_ids": ids or [], "extra": {"field": "__system/submissionDate"}}} if value else {}
    return {"connector_id": "farmer", "transport_type": "odk_central", "g2p_sender_id": "farmer-partner", "poll_state_json": state}


def test_handoff_preserves_null_and_newer_checkpoints_without_rewinding():
    empty, first, second = row(), row("2026-10-15T10:00:00Z", ["one"]), row("2026-10-15T10:01:00Z", ["two"])
    assert handoff.reconcile(empty, empty) == {}
    assert handoff.reconcile(empty, first) == first["poll_state_json"]
    assert handoff.reconcile(second, first) == second["poll_state_json"]
    assert handoff.reconcile(first, second) == second["poll_state_json"]


def test_same_timestamp_union_survives_rerun_and_rollback_direction():
    old, new = row("2026-10-15T10:00:00Z", ["one"]), row("2026-10-15T10:00:00+00:00", ["two"])
    merged = handoff.reconcile(old, new)
    assert merged["_checkpoint"]["boundary_ids"] == ["one", "two"]
    assert handoff.reconcile(old, dict(new, poll_state_json=merged)) == merged
    assert handoff.reconcile(new, dict(old, poll_state_json=merged))["_checkpoint"]["boundary_ids"] == ["one", "two"]
    assert old["poll_state_json"]["_checkpoint"]["boundary_ids"] == ["one"]


@pytest.mark.parametrize("change", ["identity", "mapping", "legacy", "field", "mode"])
def test_unknown_or_changed_checkpoint_contract_stops_handoff(change):
    old = row("2026-10-15T10:00:00Z", ["one"]); new = copy.deepcopy(old)
    if change == "identity": new["connector_id"] = "other"
    if change == "mapping": new["mapper_expression"] = "changed"
    if change == "legacy": new["poll_state_json"] = {"last_submission_id": "unknown"}
    if change == "field": new["poll_state_json"]["_checkpoint"]["extra"] = {"field": "other"}
    if change == "mode": new["poll_state_json"]["_checkpoint"]["mode"] = "sequence"
    with pytest.raises(ValueError): handoff.reconcile(old, new)
