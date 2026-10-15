"""Explicit setup: align only the existing local IAM provider with local Keycloak."""
import asyncio
import json
import os
from pathlib import Path

import asyncpg


async def main():
    provider = json.loads((Path(__file__).parent / "generated/iam-login-providers.json").read_text())[0]
    connection = await asyncpg.connect(
        host=os.environ["IAM_STAFF_DB_HOSTNAME"], port=int(os.environ["IAM_STAFF_DB_PORT"]),
        user=os.environ["IAM_STAFF_DB_USERNAME"], password=os.environ["IAM_STAFF_DB_PASSWORD"],
        database=os.environ["IAM_STAFF_DB_DBNAME"],
    )
    try:
        async with connection.transaction():
            if not await connection.fetchval("SELECT EXISTS(SELECT 1 FROM login_providers WHERE id=$1)", provider["id"]):
                raise RuntimeError("Expected local IAM provider is absent; initialize IAM first")
            # Keys are from a repository-controlled configuration, never user input.
            fields = [key for key in provider if key != "id"]
            assignments = ", ".join(f'"{key}"=${index}' for index, key in enumerate(fields, 1))
            await connection.execute(
                f"UPDATE login_providers SET {assignments}, updated_at=NOW() WHERE id=${len(fields) + 1}",
                *[provider[key] for key in fields], provider["id"],
            )
        print("Local IAM login provider aligned; other providers preserved")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
