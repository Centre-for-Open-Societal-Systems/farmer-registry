#!/usr/bin/env python3
"""Run the extension's 90_checks.sql against the deployed registry database and fail on any error.

The platform's db-seed entrypoint applies every metadata file with ON_ERROR_STOP=0,
so a failed check is only a line in the seed log. The delivery runs the checks
again after the upgrade, in the EXISTING staff API pod with that pod's database
credentials (never printed), inside a transaction that is rolled back.

On the delivery host, with the checks file, this prints the program to pipe into
the pod:

    python3 check_seed_metadata.py <90_checks.sql> | kubectl exec -i ... -- python3 -
"""

import asyncio
import json
import os
import sys

CHECKS_SQL = None


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
        command_timeout=60,
    )
    try:
        transaction = connection.transaction()
        await transaction.start()
        try:
            await connection.execute(CHECKS_SQL)
        finally:
            await transaction.rollback()
    finally:
        await connection.close()


def program(checks_path: str) -> str:
    """This file with the checks embedded, for `python3 -` in the pod."""
    with open(__file__, encoding="utf-8") as source, open(checks_path, encoding="utf-8") as checks:
        return source.read().replace("CHECKS_SQL = None", "CHECKS_SQL = " + json.dumps(checks.read()), 1)


if __name__ == "__main__":
    if CHECKS_SQL is None:
        sys.stdout.write(program(sys.argv[1]))
        sys.exit(0)
    try:
        asyncio.run(check())
    except Exception as error:
        # A check's RAISE message is safe to print; connection errors may name hosts or users.
        detail = f": {error}" if type(error).__name__ == "RaiseError" else ""
        print(f"Seed metadata checks failed: {type(error).__name__}{detail}", file=sys.stderr)
        sys.exit(1)
    print("Seed metadata checks passed (90_checks.sql).")
