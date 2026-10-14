#!/usr/bin/env python3
"""Read-only rc.544 coordinate/document schema gate in the EXISTING staff API pod.

Uses that pod's database credentials without printing them. Does not import the
application or invoke its startup/migration/seed hooks. Only schema SELECTs run
inside an explicitly read-only transaction. The asyncpg driver is in the image.
"""

import asyncio
import os
import sys

QUERY = """
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name LIKE 'g2p_register_%'
  AND column_name IN ('latitude', 'longitude', 'altitude')
ORDER BY table_name, column_name
"""
DOCUMENT_QUERY = """
SELECT data_type, is_nullable FROM information_schema.columns
WHERE table_schema='public' AND table_name='g2p_register_document_history'
  AND column_name='event_type'
"""


async def check():
    import asyncpg

    prefix = "REGISTRY_STAFF_PORTAL_API_DB_"
    required = ("HOSTNAME", "DBNAME", "USERNAME", "PASSWORD")
    if not all(os.environ.get(prefix + key) for key in required):
        raise RuntimeError("required database configuration is missing")
    connection = await asyncpg.connect(
        host=os.environ[prefix + "HOSTNAME"],
        port=int(os.environ.get(prefix + "PORT", "5432")),
        database=os.environ[prefix + "DBNAME"],
        user=os.environ[prefix + "USERNAME"],
        password=os.environ[prefix + "PASSWORD"],
        timeout=15,
        command_timeout=15,
    )
    try:
        async with connection.transaction(readonly=True):
            rows = await connection.fetch(QUERY)
            document_columns = await connection.fetch(DOCUMENT_QUERY)
    finally:
        await connection.close()
    if not rows:
        print("FAIL: no registry coordinate columns found; verify the selected database/schema")
        return 1
    incompatible = [row for row in rows if row["data_type"] not in ("real", "double precision")]
    if incompatible:
        print(f"FAIL: {len(incompatible)} coordinate columns are incompatible with rc.544:")
        for row in incompatible:
            print(f"  {row['table_name']}.{row['column_name']}: {row['data_type']}")
        print("Rehearse and run the backed-up coordinate migration before deploying rc.544; no schema was changed.")
        return 1
    print(f"Coordinate schema OK: {len(rows)} Float-compatible columns; no schema/data was changed.")
    if not document_columns or document_columns[0]["data_type"] not in ("character varying", "text") or document_columns[0]["is_nullable"] != "NO":
        print("FAIL: document history needs a non-null text event_type column for rc.544 attachment promotion.")
        print("Review ci/gen2/migrations/document_history_event_type.sql; no schema was changed.")
        return 1
    print("Document history schema OK: event_type supports attachment promotion.")
    return 0


def main():
    try:
        return asyncio.run(check())
    except Exception as error:
        # Do not include a connection string, password or raw server exception.
        print(f"FAIL: read-only coordinate schema check could not complete ({type(error).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
