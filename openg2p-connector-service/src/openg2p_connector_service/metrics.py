"""Prometheus metrics helpers.

The metrics module is a thin, optional layer. When
`CONNECTOR_METRICS_ENABLED=false` (default) or prometheus_client fails to
import, every helper becomes a cheap no-op so production paths don't pay for
observability they haven't turned on.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

from .config import get_settings

_logger = logging.getLogger(__name__)

_ENABLED = False
_REGISTRY: Any = None

# Instruments (populated in _init when enabled)
poll_duration: Any = None
poll_fetched: Any = None
poll_status_total: Any = None
ingest_records_total: Any = None
ingest_duration: Any = None
partner_requests_total: Any = None
partner_duration: Any = None
dlq_entries_total: Any = None
poll_checkpoint_lag_seconds: Any = None
poll_incremental_fallback_total: Any = None
poll_boundary_replay_skipped_total: Any = None


class _NoOp:
    """Drop-in replacement used when metrics are disabled or missing deps."""

    def labels(self, *_: Any, **__: Any) -> "_NoOp":
        return self

    def inc(self, *_: Any, **__: Any) -> None:
        return

    def observe(self, *_: Any, **__: Any) -> None:
        return

    def set(self, *_: Any, **__: Any) -> None:
        return


_NOOP = _NoOp()


def _init() -> None:
    global _ENABLED, _REGISTRY
    global poll_duration, poll_fetched, poll_status_total
    global ingest_records_total, ingest_duration
    global partner_requests_total, partner_duration, dlq_entries_total
    global poll_checkpoint_lag_seconds, poll_incremental_fallback_total
    global poll_boundary_replay_skipped_total

    settings = get_settings()
    if not settings.metrics_enabled:
        poll_duration = _NOOP
        poll_fetched = _NOOP
        poll_status_total = _NOOP
        ingest_records_total = _NOOP
        ingest_duration = _NOOP
        partner_requests_total = _NOOP
        partner_duration = _NOOP
        dlq_entries_total = _NOOP
        poll_checkpoint_lag_seconds = _NOOP
        poll_incremental_fallback_total = _NOOP
        poll_boundary_replay_skipped_total = _NOOP
        return

    try:
        from prometheus_client import (
            CollectorRegistry,
            Counter,
            Gauge,
            Histogram,
        )
    except Exception:
        _logger.warning(
            "CONNECTOR_METRICS_ENABLED=true but prometheus_client could not be imported; "
            "metrics disabled at runtime."
        )
        poll_duration = _NOOP
        poll_fetched = _NOOP
        poll_status_total = _NOOP
        ingest_records_total = _NOOP
        ingest_duration = _NOOP
        partner_requests_total = _NOOP
        partner_duration = _NOOP
        dlq_entries_total = _NOOP
        poll_checkpoint_lag_seconds = _NOOP
        poll_incremental_fallback_total = _NOOP
        poll_boundary_replay_skipped_total = _NOOP
        return

    _REGISTRY = CollectorRegistry()
    _ENABLED = True

    poll_duration = Histogram(
        "connector_poll_duration_seconds",
        "Duration of connector poll tasks in seconds.",
        ("connector_id", "transport"),
        registry=_REGISTRY,
        buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600),
    )
    poll_fetched = Counter(
        "connector_poll_records_fetched_total",
        "Total records fetched from a source during polls.",
        ("connector_id", "transport"),
        registry=_REGISTRY,
    )
    poll_status_total = Counter(
        "connector_poll_runs_total",
        "Poll task completions partitioned by terminal status.",
        ("connector_id", "status"),
        registry=_REGISTRY,
    )

    ingest_records_total = Counter(
        "connector_ingestion_records_total",
        "Records processed through the ingestion pipeline.",
        ("connector_id", "status"),
        registry=_REGISTRY,
    )
    ingest_duration = Histogram(
        "connector_ingestion_duration_seconds",
        "End-to-end ingestion duration per record (map + deliver).",
        ("connector_id",),
        registry=_REGISTRY,
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
    )

    partner_requests_total = Counter(
        "connector_partner_ingest_requests_total",
        "Outbound partner ingest requests to the registry.",
        ("connector_id", "status_class"),
        registry=_REGISTRY,
    )
    partner_duration = Histogram(
        "connector_partner_ingest_duration_seconds",
        "Partner ingest HTTP call duration in seconds.",
        ("connector_id",),
        registry=_REGISTRY,
        buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
    )

    dlq_entries_total = Counter(
        "connector_dlq_entries_total",
        "Entries written to the dead-letter queue.",
        ("connector_id",),
        registry=_REGISTRY,
    )

    poll_checkpoint_lag_seconds = Gauge(
        "connector_poll_checkpoint_lag_seconds",
        "Seconds between now() and the persisted timestamp checkpoint. "
        "-1 when the checkpoint is non-temporal (sequence/page_token/full_scan).",
        ("connector_id", "transport", "mode"),
        registry=_REGISTRY,
    )
    poll_incremental_fallback_total = Counter(
        "connector_poll_incremental_fallback_total",
        "Times a poll downgraded from strict incremental to a wider scan.",
        ("connector_id", "transport", "reason"),
        registry=_REGISTRY,
    )
    poll_boundary_replay_skipped_total = Counter(
        "connector_poll_boundary_replay_skipped_total",
        "Records skipped by the timestamp-checkpoint boundary replay window.",
        ("connector_id", "transport"),
        registry=_REGISTRY,
    )


def enabled() -> bool:
    return _ENABLED


def registry() -> Any:
    """Return the CollectorRegistry (or None if metrics are disabled)."""
    return _REGISTRY


@contextmanager
def observe(histogram: Any) -> Iterator[None]:
    """Context manager timing a block; emits into the provided histogram.

    Works with both real histograms and the _NoOp fallback.
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        histogram.observe(time.perf_counter() - t0)


_init()
