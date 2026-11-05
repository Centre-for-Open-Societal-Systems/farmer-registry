"""Copy committed source-event keys and checkpoints before restoring ingestion."""
import json
import re

from .checkpoint_handoff import reconcile


async def reconcile_stopped(source, target, connector_id, apply=False):
    left = await target.fetchrow("SELECT * FROM connector_definitions WHERE connector_id=$1", connector_id)
    right = await source.fetchrow("SELECT * FROM connector_definitions WHERE connector_id=$1", connector_id)
    if not left or not right or not left["paused"] or not right["paused"]:
        raise ValueError("Both pipeline definitions must be paused")
    for connection in (source, target):
        if await connection.fetchval("SELECT count(*) FROM ingestion_runs WHERE connector_id=$1 AND status='IN_PROGRESS'", connector_id):
            raise ValueError("In-flight runs must finish before reconciliation")
    state = reconcile(dict(left), dict(right))
    rows = await source.fetch("SELECT r.*,k.source_key FROM idempotency_keys k JOIN ingestion_runs r ON r.run_id=k.run_id WHERE k.connector_id=$1 AND r.status='SUCCESS' ORDER BY k.source_key", connector_id)
    if len(rows) != await source.fetchval("SELECT count(*) FROM idempotency_keys WHERE connector_id=$1", connector_id):
        raise ValueError("Idempotency rows must refer to committed successful runs")
    columns = await target.fetch("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='ingestion_runs' ORDER BY ordinal_position")
    columns = [r[0] for r in columns]
    if any(not re.fullmatch('[a-z_][a-z0-9_]*', name) for name in columns):
        raise ValueError("Unreviewed target columns")
    copied = 0
    transaction = target.transaction()
    await transaction.start()
    try:
        for row in rows:
            existing = await target.fetchrow("SELECT r.* FROM idempotency_keys k JOIN ingestion_runs r ON r.run_id=k.run_id WHERE k.connector_id=$1 AND k.source_key=$2", connector_id, row["source_key"])
            if existing:
                if existing["status"] != 'SUCCESS' or existing["registry_correlation_id"] != row["registry_correlation_id"]:
                    raise ValueError("Conflicting source-event acceptance")
                continue
            if await target.fetchval("SELECT count(*) FROM ingestion_runs WHERE run_id=$1", row["run_id"]):
                raise ValueError("Run identity collision requires review")
            if any(name not in row for name in columns):
                raise ValueError("Target schema cannot restore this successful run")
            await target.execute('INSERT INTO ingestion_runs ('+','.join(columns)+') VALUES ('+','.join('$'+str(i+1) for i in range(len(columns)))+')', *[row[name] for name in columns])
            await target.execute("INSERT INTO idempotency_keys(connector_id,source_key,run_id,redelivery_count) VALUES($1,$2,$3,0)", connector_id, row["source_key"], row["run_id"])
            copied += 1
        await target.execute("UPDATE connector_definitions SET poll_state_json=$2 WHERE connector_id=$1", connector_id, json.dumps(state) if state else None)
        if apply: await transaction.commit()
        else: await transaction.rollback()
    except BaseException:
        await transaction.rollback()
        raise
    return {"successfulKeysVerified": len(rows), "successfulKeysCopied": copied,
            "checkpointReconciled": True, "applied": apply, "targetRemainsPaused": True}
