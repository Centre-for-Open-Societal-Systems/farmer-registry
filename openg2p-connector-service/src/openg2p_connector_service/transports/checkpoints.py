"""Structured polling checkpoint contract.

Replaces the previous "cursor_key/cursor_value as plain strings"
convention with a transport-defined :class:`Checkpoint` so the worker no
longer has to guess what "newer" means.

Why this exists
---------------
The legacy worker advanced cursors with ``str(record.cursor_value) >
str(prev)``. That falls apart for any transport whose source order is
not lexicographically increasing strings: ISO timestamps with offsets,
opaque continuation tokens, or any composite key. It also gave us no
way to express "this transport cannot do strict incremental polling at
all", which is exactly the problem the live ODK server hit (``__id``
returns 501 for ``$filter``).

The :class:`Checkpoint` contract lets each transport declare:

* what kind of checkpoint it is producing (sequence, timestamp, page
  token, or explicit full scan), and
* how to compare/merge two checkpoints to know whether to persist a
  new one.

The worker only calls :meth:`Checkpoint.is_advanced_over` and
:meth:`Checkpoint.merged_with` — it does not contain transport
knowledge.

Persistence shape
-----------------
The structured checkpoint is stored under the reserved key
``_checkpoint`` inside ``connector_definitions.poll_state_json``::

    {
        "_checkpoint": {
            "mode": "timestamp",
            "value": "2026-04-19T10:11:12.000Z",
            "boundary_ids": ["uuid:..."],
            "extra": {...}
        },
        "last_submission_id": "uuid:..."  # legacy, still respected
    }

Legacy keys remain so existing connectors keep working until they next
emit a structured checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CheckpointMode(str, Enum):
    """How a transport tells us "I made forward progress"."""

    SEQUENCE = "sequence"
    """Monotonically increasing comparable id (UUID v7, snowflake, integer)."""

    TIMESTAMP = "timestamp"
    """ISO-8601 UTC string. Use ``boundary_ids`` to dedupe ties."""

    PAGE_TOKEN = "page_token"
    """Opaque continuation token managed by the provider (Google, Salesforce…)."""

    FULL_SCAN = "full_scan"
    """No incremental query. Worker should refuse unless explicitly opted in."""


# Reserved key inside poll_state_json for the structured checkpoint blob.
CHECKPOINT_STATE_KEY = "_checkpoint"


@dataclass
class TransportCapability:
    """Static declaration of how a transport can do incremental polling.

    Stored on each transport class so the registry can answer "is this
    transport safe for strict incremental mode?" without instantiating
    it.
    """

    modes: tuple[CheckpointMode, ...]
    default_mode: CheckpointMode
    supports_strict_incremental: bool
    notes: str = ""


@dataclass
class Checkpoint:
    """A transport-emitted checkpoint, persisted in ``poll_state_json``."""

    mode: CheckpointMode
    value: Any = None
    boundary_ids: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "value": self.value,
            "boundary_ids": list(self.boundary_ids),
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Checkpoint | None":
        if not d or not isinstance(d, dict):
            return None
        raw_mode = d.get("mode")
        if not raw_mode:
            return None
        try:
            mode = CheckpointMode(raw_mode)
        except ValueError:
            return None
        return cls(
            mode=mode,
            value=d.get("value"),
            boundary_ids=list(d.get("boundary_ids") or []),
            extra=dict(d.get("extra") or {}),
        )

    # ------------------------------------------------------------------
    # advancement / merge logic — the worker only calls these.
    # ------------------------------------------------------------------
    def is_advanced_over(self, prev: "Checkpoint | None") -> bool:
        """Return True if *self* represents progress beyond *prev*.

        The worker uses this to decide whether to persist the new
        checkpoint. ``FULL_SCAN`` never advances — it intentionally
        re-scans every poll.
        """
        if prev is None:
            return self.mode is not CheckpointMode.FULL_SCAN and self.value is not None
        if prev.mode != self.mode:
            # Mode change is a deliberate reconfiguration; accept the new one.
            return True
        if self.mode is CheckpointMode.SEQUENCE:
            return _str_or_empty(self.value) > _str_or_empty(prev.value)
        if self.mode is CheckpointMode.TIMESTAMP:
            cur = _str_or_empty(self.value)
            old = _str_or_empty(prev.value)
            if cur > old:
                return True
            if cur == old:
                # Same watermark, but new boundary ids were observed.
                new_ids = set(self.boundary_ids) - set(prev.boundary_ids)
                return bool(new_ids)
            return False
        if self.mode is CheckpointMode.PAGE_TOKEN:
            return _str_or_empty(self.value) != _str_or_empty(prev.value)
        return False

    def merged_with(self, prev: "Checkpoint | None") -> "Checkpoint":
        """Combine with *prev* so we don't lose boundary ids at a tie.

        For ``TIMESTAMP``: at the same watermark we keep the union of
        previously-seen ``boundary_ids`` so a future poll of the same
        watermark can still skip already-seen records inside the
        overlap window. Other modes return ``self`` unchanged.
        """
        if self.mode is not CheckpointMode.TIMESTAMP:
            return self
        if (
            prev is None
            or prev.mode is not CheckpointMode.TIMESTAMP
            or _str_or_empty(prev.value) != _str_or_empty(self.value)
        ):
            return self
        seen = list(prev.boundary_ids)
        for bid in self.boundary_ids:
            if bid not in seen:
                seen.append(bid)
        return Checkpoint(
            mode=self.mode,
            value=self.value,
            boundary_ids=seen,
            extra=dict(self.extra),
        )


def _str_or_empty(v: Any) -> str:
    return "" if v is None else str(v)
