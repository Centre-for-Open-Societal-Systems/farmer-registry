#!/usr/bin/env python3
"""Rehearse the actual upstream image against a disposable, isolated PostgreSQL.

The internal Docker network cannot reach Registry/ODK. The database password is
generated per run, passed through inherited environment, and never printed.
"""
import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path


SCRIPT = r'''
import asyncio,json,os,re
from unittest.mock import AsyncMock,patch
from sqlalchemy import text,select,func
from sqlalchemy.ext.asyncio import async_sessionmaker
from openg2p_connector_service.database import get_engine
from openg2p_connector_service.models import Base,ConnectorDefinition,IngestionRun,IdempotencyKey
from openg2p_connector_service import db_migrations
from openg2p_connector_service.services.ingestion_service import IngestionService

async def main():
 engine=get_engine()
 # Hash original columns only, so additive migrations can be checked without
 # ignoring changes to existing rows. Hashes and private payloads stay local.
 snapshots=[]
 if os.environ.get('REHEARSAL_RESTORED')=='true':
  async with engine.connect() as conn:
   tables=(await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"))).scalars().all()
   for table in tables:
    columns=(await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:table ORDER BY ordinal_position"),{'table':table})).scalars().all()
    assert all(re.fullmatch('[a-z_][a-z0-9_]*',name) for name in [table,*columns])
    pairs=','.join("'%s',t.\"%s\""%(column,column) for column in columns)
    query='SELECT count(*),md5(coalesce(string_agg(h,\'\' ORDER BY h),\'\')) FROM (SELECT md5(jsonb_build_object('+pairs+')::text) h FROM "'+table+'" t) s'
    snapshots.append((query,tuple((await conn.execute(text(query))).one())))
 for attempt in range(2):
  async with engine.begin() as conn:
   await conn.run_sync(Base.metadata.create_all)
   await db_migrations.apply(conn)
 # A failed migration batch must roll back its earlier DDL.
 try:
  async with engine.begin() as conn:
   await conn.execute(text('CREATE TABLE rehearsal_must_rollback (id integer)'))
   await conn.execute(text('SELECT * FROM rehearsal_deliberately_missing_table'))
 except Exception: pass
 else: raise AssertionError('Injected failure did not propagate')
 async with engine.connect() as conn:
  assert await conn.scalar(text("SELECT to_regclass('rehearsal_must_rollback')")) is None
 async with engine.begin() as conn:
  await db_migrations.apply(conn)
 async with engine.connect() as conn:
  for query,expected in snapshots:
   assert tuple((await conn.execute(text(query))).one())==expected
 factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as session:
  connector=ConnectorDefinition(connector_id='synthetic-rehearsal',name='Synthetic Rehearsal',platform='odk_central',transport_type='odk_central',paused=True,enabled=True,auth_type='none',g2p_sender_id='farmer-partner',g2p_register_mnemonic='Farmer',data_model_mnemonic='FARMER_ODK_MODEL')
  session.add(connector);await session.commit()
  send=AsyncMock(return_value='synthetic-correlation')
  with patch('openg2p_connector_service.services.ingestion_service.PartnerIngestClient.send',send):
   service=IngestionService()
   first=await service.process_record(connector,'farmer:uuid:synthetic',{'__id':'uuid:synthetic','value':'synthetic'},session)
   await session.commit()
   second=await service.process_record(connector,'farmer:uuid:synthetic',{'__id':'uuid:synthetic','value':'synthetic'},session)
   await session.commit()
   assert first.run_id==second.run_id
   assert send.await_count==1
   assert await session.scalar(select(func.count()).select_from(IngestionRun).where(IngestionRun.connector_id=='synthetic-rehearsal'))==1
   assert await session.scalar(select(func.count()).select_from(IdempotencyKey).where(IdempotencyKey.connector_id=='synthetic-rehearsal'))==1
   assert second.redelivery_count==1
 print(json.dumps({'schemaRerun':True,'failedDdlRolledBack':True,'failureRecovery':True,'duplicateSentOnce':True,'isolatedDatabases':True,'restoredSnapshot':bool(snapshots),'existingDataPreserved':bool(snapshots)}))
 await engine.dispose()
asyncio.run(main())
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    parser.add_argument('--backup',type=Path)
    args = parser.parse_args()
    image = args.image
    if args.backup and not args.backup.is_file():
        raise ValueError('Private backup file missing')
    name = "coss-connector-rehearsal-" + uuid.uuid4().hex[:12]
    env = dict(os.environ)
    env["POSTGRES_PASSWORD"] = secrets.token_urlsafe(32)
    env.update(CONNECTOR_DB_PASSWORD=env["POSTGRES_PASSWORD"], CONNECTOR_DB_HOSTNAME=name,
               CONNECTOR_DB_USERNAME="postgres", CONNECTOR_DB_DBNAME="postgres",
               CONNECTOR_DB_PORT="5432", CONNECTOR_DB_DRIVER="postgresql+asyncpg")
    created_network = created_database = False
    def run(args, **kw):
        return subprocess.run(args, env=env, check=True, capture_output=True, text=True, **kw)
    try:
        run(["docker", "pull", "postgres:16-alpine"])
        run(["docker", "network", "create", "--internal", name]); created_network = True
        mounts = ['-v',str(args.backup.resolve())+':/backup/database.dump:ro'] if args.backup else []
        run(["docker", "run", "-d", "--name", name, "--network", name,
             *mounts,"-e", "POSTGRES_PASSWORD", "postgres:16-alpine"]); created_database = True
        for _ in range(60):
            result = subprocess.run(["docker", "exec", name, "pg_isready", "-U", "postgres"], capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Isolated PostgreSQL did not start")
        if args.backup:
            run(['docker','exec',name,'pg_restore','--exit-on-error','--no-owner','--no-privileges','-U','postgres','-d','postgres','/backup/database.dump'])
            env['REHEARSAL_RESTORED']='true'
        docker_args = ["docker", "run", "--rm", "-i", "--network", name, "--entrypoint", "python","-e","REHEARSAL_RESTORED"]
        for key in ("CONNECTOR_DB_PASSWORD", "CONNECTOR_DB_HOSTNAME", "CONNECTOR_DB_USERNAME",
                    "CONNECTOR_DB_DBNAME", "CONNECTOR_DB_PORT", "CONNECTOR_DB_DRIVER"):
            docker_args.extend(["-e", key])
        result = run([*docker_args, image, "-"], input=SCRIPT)
        # Only print the fixed synthetic-check result, never captured DB errors.
        report = json.loads(result.stdout.strip().splitlines()[-1])
        print(json.dumps(report, sort_keys=True))
    finally:
        if created_database:
            subprocess.run(["docker", "rm", "-f", "-v", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if created_network:
            subprocess.run(["docker", "network", "rm", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("FAIL: isolated connector rehearsal failed; private process output withheld", file=sys.stderr)
        raise SystemExit(1)
