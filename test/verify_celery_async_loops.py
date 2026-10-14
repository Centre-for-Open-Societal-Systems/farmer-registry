"""Read-only check in a built worker: reuse its engine across task event loops."""
import asyncio
import runpy

from sqlalchemy import text

runpy.run_path("/app/run_celery.py")["get_app"]()
from openg2p_registry_celery_worker.engine import Engine


async def query():
    async with Engine.get_async_session_maker()() as session:
        assert (await session.execute(text("SELECT 1"))).scalar() == 1


for _ in range(4):
    asyncio.run(query())
print("PASS: worker async engine serves four independent event loops")
