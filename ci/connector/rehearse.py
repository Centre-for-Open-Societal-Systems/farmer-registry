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
from coss_connector import utc_timestamps
from openg2p_connector_service.worker import _poll_async

async def main():
 engine=get_engine()
 async with engine.connect() as conn:
  assert await conn.scalar(text('SELECT rolsuper FROM pg_roles WHERE rolname=current_user')) is False
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
 # Exercise the real worker's timestamp assignment/commit, not only the
 # ingestion service. Upstream writes aware UTC into a naive timestamp column.
 class EmptyTransport:
  async def fetch(self,connector):
   if False: yield None
 async with factory() as session:
  session.add(ConnectorDefinition(connector_id='synthetic-poll-clock',name='Synthetic Poll Clock',platform='odk_central',transport_type='odk_central',paused=False,enabled=True,auth_type='none'))
  await session.commit()
 with patch('openg2p_connector_service.worker.get_transport',return_value=EmptyTransport()):
  for attempt in range(2):
   result=await _poll_async('synthetic-poll-clock')
   assert result['fetched']==0 and 'poll_error' not in result
 async with factory() as session:
  polled=await session.get(ConnectorDefinition,'synthetic-poll-clock')
  assert polled.last_poll_at is not None and polled.last_poll_status=='SUCCESS'
 # A failed outbound record must stop the page before a later successful row
 # can advance its watermark past the failed boundary.
 from types import SimpleNamespace
 from openg2p_connector_service.transports.base import SourceRecord
 from openg2p_connector_service.transports.checkpoints import Checkpoint,CheckpointMode
 async with factory() as session:
  session.add(ConnectorDefinition(connector_id='synthetic-boundary',name='Synthetic Boundary',platform='odk_central',transport_type='odk_central',paused=False,enabled=True,auth_type='none'))
  await session.commit()
 class BoundaryTransport:
  async def fetch(self,connector):
   boundary=(connector.get_poll_state().get('_checkpoint') or {}).get('value','')
   for index in [1,2,3]:
    value='2026-10-15T00:00:0'+str(index)+'Z'
    if value>boundary:
     yield SourceRecord('synthetic:'+str(index),{'__id':str(index)},checkpoint=Checkpoint(mode=CheckpointMode.TIMESTAMP,value=value,boundary_ids=[str(index)]))
 calls=[]
 async def process(*args,**kwargs):
  identity=kwargs['source_event_id'];calls.append(identity)
  failed=identity=='synthetic:2' and calls.count(identity)==1
  return SimpleNamespace(status=SimpleNamespace(value='FAILED' if failed else 'SUCCESS'))
 with patch('openg2p_connector_service.worker.get_transport',return_value=BoundaryTransport()),patch.object(IngestionService,'process_record',side_effect=process):
  first=await _poll_async('synthetic-boundary')
  assert first['fetched']==2 and first['failed']==1
  async with factory() as session:
   boundary=await session.get(ConnectorDefinition,'synthetic-boundary')
   assert boundary.get_poll_state()['_checkpoint']['value']=='2026-10-15T00:00:01Z'
  second=await _poll_async('synthetic-boundary')
  assert second['fetched']==2 and second['failed']==0
  assert calls==['synthetic:1','synthetic:2','synthetic:2','synthetic:3']
 # Reconcile a successful event/checkpoint into an isolated recovery database,
 # prove a key-insert failure rolls back the earlier run write, then rerun.
 import asyncpg
 from sqlalchemy.ext.asyncio import create_async_engine
 from coss_connector.recovery import reconcile_stopped
 recovery_engine=create_async_engine(engine.url.set(database='connector_recovery'))
 async with recovery_engine.begin() as c:
  await c.run_sync(Base.metadata.create_all);await db_migrations.apply(c)
 recovery_factory=async_sessionmaker(recovery_engine,expire_on_commit=False)
 async with recovery_factory() as session:
  session.add(ConnectorDefinition(connector_id='synthetic-rehearsal',name='Synthetic Rehearsal',platform='odk_central',transport_type='odk_central',paused=True,enabled=True,auth_type='none',g2p_sender_id='farmer-partner',g2p_register_mnemonic='Farmer',data_model_mnemonic='FARMER_ODK_MODEL'))
  await session.commit()
 parameters=dict(host=os.environ['CONNECTOR_DB_HOSTNAME'],port=int(os.environ['CONNECTOR_DB_PORT']),user=os.environ['CONNECTOR_DB_USERNAME'],password=os.environ['CONNECTOR_DB_PASSWORD'])
 source=await asyncpg.connect(**parameters,database=os.environ['CONNECTOR_DB_DBNAME'])
 target=await asyncpg.connect(**parameters,database='connector_recovery')
 await target.execute("CREATE FUNCTION synthetic_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected'; END $$; CREATE TRIGGER synthetic_failure BEFORE INSERT ON idempotency_keys FOR EACH ROW EXECUTE FUNCTION synthetic_failure()")
 try: await reconcile_stopped(source,target,'synthetic-rehearsal',apply=True)
 except Exception: pass
 else: raise AssertionError('Injected recovery failure did not propagate')
 assert await target.fetchval('SELECT count(*) FROM ingestion_runs')==0
 await target.execute('DROP TRIGGER synthetic_failure ON idempotency_keys; DROP FUNCTION synthetic_failure()')
 first=await reconcile_stopped(source,target,'synthetic-rehearsal',apply=True)
 second=await reconcile_stopped(source,target,'synthetic-rehearsal',apply=True)
 assert first['successfulKeysCopied']==1 and second['successfulKeysCopied']==0
 assert await target.fetchval('SELECT count(*) FROM idempotency_keys')==1
 await source.close();await target.close();await recovery_engine.dispose()
 print(json.dumps({'schemaRerun':True,'failedDdlRolledBack':True,'failureRecovery':True,'rollbackReconciled':True,'duplicateSentOnce':True,'failedBoundaryRetried':True,'pollTimestampPersisted':True,'applicationRole':True,'isolatedDatabases':True,'restoredSnapshot':bool(snapshots),'existingDataPreserved':bool(snapshots)}))
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
    env.update(CONNECTOR_DB_PASSWORD=secrets.token_urlsafe(32), CONNECTOR_DB_HOSTNAME=name,
               CONNECTOR_DB_USERNAME="connector_rehearsal_user", CONNECTOR_DB_DBNAME="connector_rehearsal",
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
            # The image's temporary init server accepts Unix sockets before
            # shutting down and starting the final TCP listener. Other
            # containers can use only TCP; do not race that initialization.
            result = subprocess.run(["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"], capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Isolated PostgreSQL did not start")
        # Exercise migrations with a database-owning application role rather
        # than the PostgreSQL superuser used to create the disposable fixture.
        credential = env['CONNECTOR_DB_PASSWORD'].replace("'", "''")
        run(['docker','exec','-i',name,'psql','-v','ON_ERROR_STOP=1','-U','postgres','-d','postgres'],
            input="CREATE ROLE connector_rehearsal_user LOGIN PASSWORD '" + credential + "';\n"
                  "CREATE DATABASE connector_rehearsal OWNER connector_rehearsal_user;\n"
                  "CREATE DATABASE connector_recovery OWNER connector_rehearsal_user;\n")
        if args.backup:
            run(['docker','exec',name,'pg_restore','--exit-on-error','--no-owner','--no-privileges',
                 '--role','connector_rehearsal_user','-U','postgres','-d','connector_rehearsal','/backup/database.dump'])
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
