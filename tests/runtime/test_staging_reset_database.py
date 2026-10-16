"""Real PostgreSQL 16 reset/recovery rehearsal, using a disposable Docker container.

Run on a trusted Docker host: python tests/runtime/test_staging_reset_database.py
No ports, application credentials, external APIs or shared database are used.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('staging_reset', ROOT / 'scripts/operations/staging/reset_registry.py')
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)
name = 'farmer-reset-rehearsal-' + uuid.uuid4().hex[:12]


def command(args, text=None):
    result = subprocess.run(args, input=text, text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError('Disposable reset rehearsal command failed: ' + result.stderr)
    return result.stdout


def sql(query, database='postgres'):
    return command(['docker', 'exec', '-i', name, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', database], query)


try:
    command(['docker', 'run', '-d', '--name', name, '--network', 'none', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', 'postgres:16'])
    for _ in range(60):
        ready = subprocess.run(['docker', 'exec', name, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'], capture_output=True)
        if ready.returncode == 0: break
        time.sleep(1)
    else: raise RuntimeError('Disposable PostgreSQL did not start')
    reset.sql = sql
    sql('CREATE ROLE farmer_owner; CREATE ROLE farmer_reader; CREATE DATABASE farmer_registry_far OWNER farmer_owner; CREATE DATABASE unrelated_registry;')
    sql('GRANT CONNECT ON DATABASE farmer_registry_far TO farmer_reader; ALTER DATABASE farmer_registry_far SET statement_timeout TO \'90s\'; ALTER ROLE farmer_owner IN DATABASE farmer_registry_far SET search_path TO \'public\';')
    sql('CREATE TABLE old_rows(id int); INSERT INTO old_rows VALUES(1);', reset.DATABASE)
    sql('CREATE TABLE untouched(id int); INSERT INTO untouched VALUES(42);', 'unrelated_registry')
    original = reset.properties(reset.DATABASE)
    candidate, archive = reset.names('rehearsal01')
    sql(reset.creation_sql(candidate, original))
    prepared = reset.properties(candidate)
    assert all(original[k] == prepared[k] for k in reset.PROPERTIES)
    sql('CREATE TABLE sample_rows(id int); INSERT INTO sample_rows VALUES(21);', candidate)
    sql(reset.swap_sql(candidate, archive, original['oid'], prepared['oid']))
    assert reset.properties(reset.DATABASE)['oid'] == prepared['oid']
    assert sql('SELECT id FROM sample_rows', reset.DATABASE).strip() == '21'
    assert sql('SELECT id FROM untouched', 'unrelated_registry').strip() == '42'
    assert sql("SELECT datallowconn FROM pg_database WHERE datname='" + archive + "'").strip() == 'f'
    # Repeat exchange is rejected; it cannot accidentally reset the fresh DB twice.
    try: sql(reset.swap_sql(candidate, archive, original['oid'], prepared['oid']))
    except RuntimeError: pass
    else: raise AssertionError('Repeated exchange was accepted')
    assert sql('SELECT id FROM sample_rows', reset.DATABASE).strip() == '21'
    # A failed rename rolls back both names; the explicit connection fence persists.
    sql('CREATE DATABASE farmer_registry_far_reset_failure; CREATE DATABASE farmer_registry_far_archive_conflict;')
    failure = reset.properties('farmer_registry_far_reset_failure')
    statement = reset.swap_sql('farmer_registry_far_reset_failure', 'farmer_registry_far_archive_failure', prepared['oid'], failure['oid'])
    statement = statement.replace('BEGIN;\nALTER', 'BEGIN;\nSELECT definitely_missing_reset_probe();\nALTER')
    try: sql(statement)
    except RuntimeError: pass
    else: raise AssertionError('Injected failure did not abort')
    assert sql("SELECT datallowconn FROM pg_database WHERE datname='farmer_registry_far'").strip() == 'f'
    assert reset.properties(reset.DATABASE)['oid'] == prepared['oid']
    # Recovery restores the retained original and keeps the replacement separately.
    sql('BEGIN; ALTER DATABASE farmer_registry_far RENAME TO farmer_registry_far_reset_recovery; ALTER DATABASE ' + reset.ident(archive) + ' RENAME TO farmer_registry_far; ALTER DATABASE farmer_registry_far WITH ALLOW_CONNECTIONS true; COMMIT;')
    assert sql('SELECT id FROM old_rows', reset.DATABASE).strip() == '1'
    assert reset.properties(reset.DATABASE)['oid'] == original['oid']
    assert sql('SELECT id FROM untouched', 'unrelated_registry').strip() == '42'
    print(json.dumps({'postgres': 16, 'databasePropertiesPreserved': True, 'atomicExchange': True,
        'repeatRejected': True, 'injectedFailureFenced': True, 'originalRestored': True,
        'unrelatedRegistryPreserved': True, 'noDatabaseDropped': True}))
finally:
    subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
