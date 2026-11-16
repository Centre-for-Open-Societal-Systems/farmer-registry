"""The TEMP- re-publish task reads a bounded window of outgoing snapshots and batches its farmers."""
import asyncio
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

_path = Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension/fr_id_republish.py"
_spec = importlib.util.spec_from_file_location("oan_fr_id_republish_test", _path)
republish = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(republish)


def test_pending_reads_only_recent_temp_snapshots():
    now = datetime(2026, 11, 16, 10, 0)
    params = republish.pending_params(now=now)
    assert params["since"] == now - timedelta(days=republish.SCAN_DAYS)
    assert params["limit"] == republish.BATCH_SIZE
    temp_clause = republish.PENDING_SQL.split("LIKE 'TEMP-%'")[0]
    assert "o.created_at >= :since" in temp_clause


def test_every_bound_parameter_is_supplied():
    names = set(__import__("re").findall(r":([a-z_]+)", republish.PENDING_SQL))
    assert names <= set(republish.pending_params())


class _Session:
    def __init__(self):
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def test_failing_farmer_does_not_stop_the_batch():
    session = _Session()
    queries = SimpleNamespace(
        pending=AsyncMock(return_value=["a", "b"]),
        definition=AsyncMock(return_value="definition"),
        farmer=AsyncMock(side_effect=lambda _s, rid: SimpleNamespace(
            internal_record_id=rid, functional_record_id="FR-1", last_approved_by=None, last_approved_at=None)))
    fanout = AsyncMock(side_effect=[RuntimeError("boom"), None])
    done = asyncio.run(republish._republish(lambda: session, fanout=fanout, queries=queries))
    assert done == 1
    session.rollback.assert_awaited_once()
    assert fanout.call_args.kwargs["change_request_id"] == republish.source_id("b")
