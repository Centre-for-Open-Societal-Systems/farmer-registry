"""Deterministic checkpoint reconciliation for stopped old/replacement workers.

The operator exports rows privately and applies this result transactionally.
Never resume ingestion until successful run/idempotency rows have also migrated.
"""
import copy
from datetime import datetime
import json

IDENTITY_FIELDS = ("connector_id", "platform", "transport_type", "data_model_mnemonic",
                   "mapper_expression", "mapper_version", "g2p_sender_id", "g2p_register_mnemonic")


def checkpoint(value):
    state = json.loads(value) if isinstance(value, str) else (value or {})
    if not isinstance(state, dict):
        raise ValueError("Invalid checkpoint state")
    current = state.get("_checkpoint")
    if current:
        if current.get("mode") != "timestamp" or not isinstance(current.get("value"), str):
            raise ValueError("Only reviewed ODK timestamp checkpoints may be reconciled")
        datetime.fromisoformat(current["value"].replace("Z", "+00:00"))
        ids = current.get("boundary_ids", [])
        if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
            raise ValueError("Invalid boundary IDs")
    elif state:
        raise ValueError("Legacy checkpoint requires explicit reconciliation")
    return copy.deepcopy(state)


def reconcile(old, replacement):
    if any(old.get(field) != replacement.get(field) for field in IDENTITY_FIELDS):
        raise ValueError("Pipeline identity or mapping changed")
    left, right = checkpoint(old.get("poll_state_json")), checkpoint(replacement.get("poll_state_json"))
    a, b = left.get("_checkpoint"), right.get("_checkpoint")
    if not a: return right
    if not b: return left
    first = datetime.fromisoformat(a["value"].replace("Z", "+00:00"))
    second = datetime.fromisoformat(b["value"].replace("Z", "+00:00"))
    if first > second: return left
    if second > first: return right
    if a.get("extra", {}) != b.get("extra", {}):
        raise ValueError("Checkpoint field/transport differs")
    left["_checkpoint"]["boundary_ids"] = sorted(set(a.get("boundary_ids", [])) | set(b.get("boundary_ids", [])))
    return left
