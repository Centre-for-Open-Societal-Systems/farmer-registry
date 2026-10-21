"""Bootstrap an empty DB with exact RC images on an internal-only Docker network.

Requires --api-image/--seed-image pinned by digest and a new protected --directory.
This uses db_seed metadata only; no fixture, sample, image or shared-service import.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-image', required=True)
    parser.add_argument('--seed-image', required=True)
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    for component, image in [('staff-api', args.api_image), ('db-seed', args.seed_image)]:
        if not re.fullmatch(r'\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com/openg2p/farmer-registry/' + component + r'(?::[a-f0-9]{12})?@sha256:[a-f0-9]{64}', image):
            raise ValueError('Exact accepted Registry image digest required')
    args.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    network = 'farmer-reset-bootstrap-' + uuid.uuid4().hex[:12]
    pg, database = network + '-pg', 'coss_seed_rehearsal_reset'
    report = {'apiImage': args.api_image, 'seedImage': args.seed_image,
              'isolatedNetwork': True, 'metadataOnly': True}
    sequence = 0
    def run(command, label, data=None):
        nonlocal sequence
        sequence += 1
        result = subprocess.run(command, input=data, capture_output=True, text=True, timeout=600)
        (args.directory / f'{sequence:02}-{label}.log').write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError('Reset bootstrap failed at ' + label + '; protected output retained')
        return result.stdout
    def sql(query):
        return run(['docker', 'exec', '-i', pg, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', database], 'sql', query)
    try:
        run(['docker', 'network', 'create', '--internal', network], 'network')
        run(['docker', 'run', '-d', '--name', pg, '--network', network,
             '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-v', str(ROOT) + ':/repo:ro', 'postgres:16'], 'postgres')
        for _ in range(60):
            if subprocess.run(['docker', 'exec', pg, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'], capture_output=True).returncode == 0:
                break
            time.sleep(.5)
        else:
            raise RuntimeError('Isolated PostgreSQL did not start')
        run(['docker', 'exec', pg, 'createdb', '-U', 'postgres', database], 'empty-database')
        sql('CREATE EXTENSION IF NOT EXISTS pg_trgm;')
        env = {'REGISTRY_STAFF_PORTAL_API_DB_DRIVER': 'postgresql+asyncpg',
               'REGISTRY_STAFF_PORTAL_API_DB_HOSTNAME': pg, 'REGISTRY_STAFF_PORTAL_API_DB_PORT': '5432',
               'REGISTRY_STAFF_PORTAL_API_DB_DBNAME': database, 'REGISTRY_STAFF_PORTAL_API_DB_USERNAME': 'postgres',
               'REGISTRY_STAFF_PORTAL_API_DB_PASSWORD': 'disposable-rehearsal',
               'REGISTRY_STAFF_PORTAL_API_AUDIT_ENABLED': 'false'}
        flags = [item for key, value in env.items() for item in ('-e', key + '=' + value)]
        app = ['docker', 'run', '--rm', '--network', network, *flags, '--entrypoint', 'python3', args.api_image,
               '-m', 'openg2p_registry_staff_api.main', 'migrate']
        run(app, 'application-bootstrap')
        run(app, 'application-bootstrap-rerun')
        run(['docker', 'exec', pg, 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', database,
             '-f', '/repo/scripts/operations/commons/migrations/document_history_event_type.sql'], 'document-history')
        seed_env = {'PGHOST': pg, 'PGPORT': '5432', 'PGDATABASE': database, 'PGUSER': 'postgres',
                    'PGPASSWORD': 'disposable-rehearsal', 'LOAD_GEO_DATA': 'false', 'LOAD_SAMPLE_DATA': 'false',
                    'LOAD_IMAGES': 'false', 'AWE_DB_SEED_ENABLED': 'false', 'SYNC_GEO_WIDGETS': 'false', 'LOAD_TEMPLATES': 'false'}
        flags = [item for key, value in seed_env.items() for item in ('-e', key + '=' + value)]
        seed = ['docker', 'run', '--rm', '--network', network, *flags, args.seed_image]
        run(seed, 'metadata-seed')
        run(seed, 'metadata-seed-rerun')
        run(['docker', 'exec', pg, 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', database,
             '-f', '/repo/docker/db-seed/reporting_views.sql'], 'reporting')
        counts = json.loads(sql("SELECT json_build_object('farmers',(SELECT count(*) FROM g2p_register_farmers),'intakes',(SELECT count(*) FROM g2p_intake_form_farmers),'metadata',(SELECT count(*) FROM g2p_register_definitions),'coordinates',(SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name ~ '^g2p_(register_|register_history_|intake_form_)(farmers|households|household_members|lands)$' AND column_name IN ('latitude','longitude','altitude') AND data_type IN ('real','double precision')))").strip())
        if counts['farmers'] != 0 or counts['intakes'] != 0 or counts['metadata'] < 1 or counts['coordinates'] != 36:
            raise RuntimeError('Bootstrap did not produce an empty compatible register')
        module = importlib.util.spec_from_file_location('reset_runtime', ROOT / 'scripts/operations/staging/reset_registry.py')
        reset = importlib.util.module_from_spec(module)
        module.loader.exec_module(reset)
        reset.sql = lambda query, _database: sql(query)
        reset.schema_ready(database)
        before = reset.fingerprint(database)
        run(['docker', 'run', '--rm', '--network', network, *flags, '-v', str(ROOT) + ':/repo:ro',
             '--entrypoint', 'python3', args.seed_image, '/repo/tests/runtime/test_seed_transaction.py'], 'transaction-failure-and-rerun')
        if reset.fingerprint(database) != before:
            raise RuntimeError('Failure-recovery rehearsal changed sealed candidate data/schema')
        report.update(emptyDatabaseBootstrap=True, migrationRerun=True, metadataSeed=True,
                      metadataRerun=True, reporting=True, seedTransactionRecovery=True,
                      counts=counts, complete=True)
    finally:
        (args.directory / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        subprocess.run(['docker', 'rm', '-f', pg], capture_output=True)
        subprocess.run(['docker', 'network', 'rm', network], capture_output=True)
    print(json.dumps(report))


if __name__ == '__main__':
    os.umask(0o077)
    main()
