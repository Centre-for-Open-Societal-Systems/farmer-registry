"""Unit tests for the structured polling checkpoint contract.

These cover the comparison/merge rules the worker relies on so future
transport authors can add a transport without re-implementing
"is this newer?" logic.
"""

from __future__ import annotations

from openg2p_connector_service.transports.checkpoints import (
    Checkpoint,
    CheckpointMode,
)


# ---------------------------------------------------------------------------
# round-trip
# ---------------------------------------------------------------------------

def test_to_dict_from_dict_roundtrip():
    cp = Checkpoint(
        mode=CheckpointMode.TIMESTAMP,
        value="2026-04-19T10:11:12.000Z",
        boundary_ids=["uuid:a", "uuid:b"],
        extra={"field": "__system/submissionDate"},
    )
    restored = Checkpoint.from_dict(cp.to_dict())
    assert restored == cp


def test_from_dict_handles_garbage():
    assert Checkpoint.from_dict(None) is None
    assert Checkpoint.from_dict({}) is None
    assert Checkpoint.from_dict({"mode": "not-a-mode"}) is None


# ---------------------------------------------------------------------------
# advancement
# ---------------------------------------------------------------------------

def test_sequence_advances_lexicographically():
    prev = Checkpoint(mode=CheckpointMode.SEQUENCE, value="aaa")
    new = Checkpoint(mode=CheckpointMode.SEQUENCE, value="aab")
    assert new.is_advanced_over(prev) is True
    assert prev.is_advanced_over(new) is False
    assert new.is_advanced_over(new) is False


def test_timestamp_advances_when_strictly_newer():
    prev = Checkpoint(
        mode=CheckpointMode.TIMESTAMP,
        value="2026-04-19T10:00:00Z",
        boundary_ids=["a"],
    )
    new = Checkpoint(
        mode=CheckpointMode.TIMESTAMP,
        value="2026-04-19T10:00:01Z",
        boundary_ids=["b"],
    )
    assert new.is_advanced_over(prev) is True


def test_timestamp_advances_at_same_watermark_only_with_new_boundary_ids():
    prev = Checkpoint(
        mode=CheckpointMode.TIMESTAMP,
        value="2026-04-19T10:00:00Z",
        boundary_ids=["a"],
    )
    same_known_id = Checkpoint(
        mode=CheckpointMode.TIMESTAMP,
        value="2026-04-19T10:00:00Z",
        boundary_ids=["a"],
    )
    same_new_id = Checkpoint(
        mode=CheckpointMode.TIMESTAMP,
        value="2026-04-19T10:00:00Z",
        boundary_ids=["b"],
    )
    assert same_known_id.is_advanced_over(prev) is False
    assert same_new_id.is_advanced_over(prev) is True


def test_page_token_advances_on_change():
    prev = Checkpoint(mode=CheckpointMode.PAGE_TOKEN, value="tok-1")
    same = Checkpoint(mode=CheckpointMode.PAGE_TOKEN, value="tok-1")
    new = Checkpoint(mode=CheckpointMode.PAGE_TOKEN, value="tok-2")
    assert same.is_advanced_over(prev) is False
    assert new.is_advanced_over(prev) is True


def test_full_scan_never_advances():
    prev = Checkpoint(mode=CheckpointMode.FULL_SCAN, value=None)
    new = Checkpoint(mode=CheckpointMode.FULL_SCAN, value="anything")
    assert new.is_advanced_over(prev) is False
    assert new.is_advanced_over(None) is False


def test_mode_change_is_treated_as_advancement():
    prev = Checkpoint(mode=CheckpointMode.SEQUENCE, value="aaa")
    new = Checkpoint(
        mode=CheckpointMode.TIMESTAMP, value="2026-04-19T10:00:00Z"
    )
    assert new.is_advanced_over(prev) is True


# ---------------------------------------------------------------------------
# merge — boundary id accumulation
# ---------------------------------------------------------------------------

def test_merged_with_accumulates_boundary_ids_at_same_watermark():
    prev = Checkpoint(
        mode=CheckpointMode.TIMESTAMP,
        value="2026-04-19T10:00:00Z",
        boundary_ids=["a"],
    )
    new = Checkpoint(
        mode=CheckpointMode.TIMESTAMP,
        value="2026-04-19T10:00:00Z",
        boundary_ids=["b"],
    )
    merged = new.merged_with(prev)
    assert merged.value == "2026-04-19T10:00:00Z"
    assert merged.boundary_ids == ["a", "b"]


def test_merged_with_resets_boundary_ids_at_new_watermark():
    prev = Checkpoint(
        mode=CheckpointMode.TIMESTAMP,
        value="2026-04-19T10:00:00Z",
        boundary_ids=["a", "b"],
    )
    new = Checkpoint(
        mode=CheckpointMode.TIMESTAMP,
        value="2026-04-19T10:00:01Z",
        boundary_ids=["c"],
    )
    merged = new.merged_with(prev)
    assert merged.value == "2026-04-19T10:00:01Z"
    assert merged.boundary_ids == ["c"]


def test_merged_with_is_a_no_op_for_non_timestamp_modes():
    prev = Checkpoint(mode=CheckpointMode.SEQUENCE, value="aaa")
    new = Checkpoint(mode=CheckpointMode.SEQUENCE, value="aab")
    assert new.merged_with(prev) is new
