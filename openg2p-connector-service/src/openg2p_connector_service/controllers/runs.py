"""Observability / admin endpoints for ingestion runs and DLQ."""

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, func, or_, select

from ..database import get_session_factory
from ..models import ConnectorDefinition, DeadLetterEntry, IngestionRun, RunStatus
from ..schemas import DLQEntryRead, DLQPage, IngestionRunRead, ReplayRequest, RunsPage
from ..services import IngestionService

router = APIRouter(tags=["runs"])
_ingestion = IngestionService()

MAX_PAGE = 100


def _ingestion_run_read(
    run: IngestionRun,
    connector_name: str | None,
    *,
    include_payload: bool,
) -> IngestionRunRead:
    payload = None
    if include_payload and run.run_payload_json:
        try:
            payload = json.loads(run.run_payload_json)
        except json.JSONDecodeError:
            payload = {"_error": "invalid JSON in run_payload_json"}
    data = IngestionRunRead.model_validate(run).model_dump()
    data["connector_name"] = connector_name
    data["run_payload"] = payload if include_payload else None
    return IngestionRunRead(**data)


def _dlq_read(entry: DeadLetterEntry, connector_name: str | None) -> DLQEntryRead:
    data = DLQEntryRead.model_validate(entry).model_dump()
    data["connector_name"] = connector_name
    return DLQEntryRead(**data)


def _run_status_filter(status: str) -> RunStatus:
    s = status.strip()
    try:
        return RunStatus(s)
    except ValueError:
        try:
            return RunStatus(s.upper())
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}",
            ) from exc


@router.get("/runs", response_model=RunsPage)
async def list_runs(
    connector_id: str | None = None,
    status: str | None = None,
    q: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_PAGE),
    include_payload: bool = False,
    sort: str = Query("desc"),
    order_by: str = Query(
        "time",
        description="time = updated_at (latest activity); connector = group by connector name then updated_at",
    ),
):
    if sort not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="sort must be asc or desc")
    if order_by not in ("time", "connector"):
        raise HTTPException(
            status_code=400,
            detail="order_by must be time or connector",
        )

    filters: list = []
    if connector_id:
        filters.append(IngestionRun.connector_id == connector_id)
    if status:
        filters.append(IngestionRun.status == _run_status_filter(status))
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                IngestionRun.source_event_id.ilike(like),
                IngestionRun.run_id.ilike(like),
                IngestionRun.registry_correlation_id.ilike(like),
            )
        )
    if created_from is not None:
        filters.append(IngestionRun.created_at >= created_from)
    if created_to is not None:
        filters.append(IngestionRun.created_at <= created_to)

    async with get_session_factory()() as session:
        count_stmt = select(func.count()).select_from(IngestionRun)
        if filters:
            count_stmt = count_stmt.where(and_(*filters))
        total = (await session.execute(count_stmt)).scalar_one()

        time_order = (
            IngestionRun.updated_at.desc()
            if sort == "desc"
            else IngestionRun.updated_at.asc()
        )
        stmt = (
            select(IngestionRun, ConnectorDefinition.name)
            .outerjoin(
                ConnectorDefinition,
                IngestionRun.connector_id == ConnectorDefinition.connector_id,
            )
        )
        if filters:
            stmt = stmt.where(and_(*filters))
        if order_by == "connector":
            stmt = stmt.order_by(
                ConnectorDefinition.name.asc().nulls_last(),
                time_order,
            )
        else:
            stmt = stmt.order_by(time_order)
        stmt = stmt.offset(offset).limit(limit)
        result = await session.execute(stmt)
        rows = result.all()
        items = [
            _ingestion_run_read(r, name, include_payload=include_payload)
            for r, name in rows
        ]
        return RunsPage(items=items, total=int(total))


@router.get("/runs/{run_id}", response_model=IngestionRunRead)
async def get_run(
    run_id: str,
    include_payload: bool = True,
):
    async with get_session_factory()() as session:
        stmt = (
            select(IngestionRun, ConnectorDefinition.name)
            .outerjoin(
                ConnectorDefinition,
                IngestionRun.connector_id == ConnectorDefinition.connector_id,
            )
            .where(IngestionRun.run_id == run_id)
        )
        row = (await session.execute(stmt)).one_or_none()
        if row is None:
            raise HTTPException(404, "Run not found")
        run, name = row
        return _ingestion_run_read(run, name, include_payload=include_payload)


@router.get("/dlq", response_model=DLQPage)
async def list_dlq(
    connector_id: str | None = None,
    error_category: str | None = None,
    q: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_PAGE),
    sort: str = Query("desc"),
    order_by: str = Query(
        "time",
        description="time = created_at only; connector = group by connector name",
    ),
):
    if sort not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="sort must be asc or desc")
    if order_by not in ("time", "connector"):
        raise HTTPException(
            status_code=400,
            detail="order_by must be time or connector",
        )

    filters: list = []
    if connector_id:
        filters.append(DeadLetterEntry.connector_id == connector_id)
    if error_category:
        filters.append(DeadLetterEntry.error_category == error_category)
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                DeadLetterEntry.dl_id.ilike(like),
                DeadLetterEntry.source_event_id.ilike(like),
                DeadLetterEntry.error.ilike(like),
            )
        )
    if created_from is not None:
        filters.append(DeadLetterEntry.created_at >= created_from)
    if created_to is not None:
        filters.append(DeadLetterEntry.created_at <= created_to)

    async with get_session_factory()() as session:
        count_stmt = select(func.count()).select_from(DeadLetterEntry)
        if filters:
            count_stmt = count_stmt.where(and_(*filters))
        total = (await session.execute(count_stmt)).scalar_one()

        time_order = (
            DeadLetterEntry.created_at.desc()
            if sort == "desc"
            else DeadLetterEntry.created_at.asc()
        )
        stmt = (
            select(DeadLetterEntry, ConnectorDefinition.name)
            .outerjoin(
                ConnectorDefinition,
                DeadLetterEntry.connector_id == ConnectorDefinition.connector_id,
            )
        )
        if filters:
            stmt = stmt.where(and_(*filters))
        if order_by == "connector":
            stmt = stmt.order_by(
                ConnectorDefinition.name.asc().nulls_last(),
                time_order,
            )
        else:
            stmt = stmt.order_by(time_order)
        stmt = stmt.offset(offset).limit(limit)
        result = await session.execute(stmt)
        rows = result.all()
        items = [_dlq_read(e, name) for e, name in rows]
        return DLQPage(items=items, total=int(total))


@router.get("/dlq/{dl_id}", response_model=DLQEntryRead)
async def get_dlq_entry(dl_id: str):
    async with get_session_factory()() as session:
        stmt = (
            select(DeadLetterEntry, ConnectorDefinition.name)
            .outerjoin(
                ConnectorDefinition,
                DeadLetterEntry.connector_id == ConnectorDefinition.connector_id,
            )
            .where(DeadLetterEntry.dl_id == dl_id)
        )
        row = (await session.execute(stmt)).one_or_none()
        if row is None:
            raise HTTPException(404, "DLQ entry not found")
        entry, name = row
        return _dlq_read(entry, name)


@router.post("/dlq/replay")
async def replay_dlq(body: ReplayRequest):
    """Re-process selected dead-letter entries.

    One transaction per item: long multi-replay batches otherwise leave the async
    SQLAlchemy session / connection in a bad state (e.g. after rollbacks inside
    :meth:`IngestionService.process_record`).
    """
    results = []
    for dl_id in body.dl_ids:
        async with get_session_factory()() as session:
            entry: DeadLetterEntry | None = await session.get(DeadLetterEntry, dl_id)
            if entry is None:
                results.append({"dl_id": dl_id, "error": "not found"})
                continue
            connector = await session.get(ConnectorDefinition, entry.connector_id)
            if connector is None:
                results.append({"dl_id": dl_id, "error": "connector not found"})
                continue
            run = await _ingestion.process_record(
                connector=connector,
                source_event_id=entry.source_event_id,
                raw_data=entry.payload or {},
                session=session,
            )
            if run.status.value == "SUCCESS":
                await session.delete(entry)
            results.append({"dl_id": dl_id, "run_id": run.run_id, "status": run.status.value})
            await session.commit()
    return {"replayed": results}
