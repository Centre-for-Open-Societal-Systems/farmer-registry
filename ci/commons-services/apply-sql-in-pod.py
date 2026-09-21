"""Run the SQL on stdin against the master-data database, from inside the
master-data-api pod.

upgrade.sh runs this with `kubectl exec -i ... -- python -c "$(cat this)" < file.sql`.
The pod is the one place that already has the database settings, under either
the old GEN2_MASTER_DATA_API_ prefix or the current MASTER_DATA_API_ one, and
ships asyncpg, so nothing is copied out of the cluster. The whole file is sent
as one simple-protocol query, so it may hold several statements and its own
BEGIN/COMMIT.
"""
import asyncio
import os
import sys

import asyncpg


def setting(suffix, default=None):
    for key, value in os.environ.items():
        if key.endswith("MASTER_DATA_API_DB_" + suffix):
            return value
    if default is None:
        sys.exit("no *MASTER_DATA_API_DB_%s in the pod environment" % suffix)
    return default


async def main(sql):
    conn = await asyncpg.connect(
        host=setting("HOSTNAME"),
        port=int(setting("PORT", "5432")),
        user=setting("USERNAME"),
        password=setting("PASSWORD"),
        database=setting("DBNAME"),
    )
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


if __name__ == "__main__":
    statements = sys.stdin.read()
    asyncio.run(main(statements))
    print("applied %d statement(s)" % statements.count(";"))
