#!/usr/bin/env python3
"""Prepare and exchange ONLY the Farmer staging database; never drop its archive.

Run from the promoted staging checkout on the trusted staging host. Private state,
SQL, dumps and Jobs must not be published as CI artifacts. This does not enter
maintenance, seed shared services, reset ODK or start a connector scheduler.
"""
import argparse
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'ci'))
sys.path.insert(0, str(ROOT / 'ci/deploy'))
from environments import validate_cluster, validate_release
from staging import delivery_hash
import yaml

DATABASE = 'farmer_registry_far'
PREFIX = DATABASE + '_reset_'
ARCHIVE = DATABASE + '_archive_'
PROPERTIES = ('owner', 'encoding', 'collation', 'ctype', 'provider', 'icuLocale',
              'tablespace', 'connectionLimit', 'acl', 'settings')
CHECKS = ('resetAuthorized', 'isolatedBootstrapPassed', 'metadataSeedPassed',
          'emptyRegisterVerified', 'allEnabledHooksRehearsed', 'failureRecoveryPassed',
          'registryBackupRestored', 'connectorBackupRestored', 'durableCopiesVerified',
          'farmerMaintenance', 'farmerWritersPaused', 'legacyIngestionStopped',
          'oldQueueDrained', 'farmerWorkflowCallbacksIsolated', 'partnerAndKeysReady')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')
    Path(path).chmod(0o600)


def command(args, data=None):
    result = subprocess.run(args, input=data, capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise RuntimeError('Operation failed; private command output withheld')
    return result.stdout


def ident(value):
    return '"' + value.replace('"', '""') + '"'


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def names(token):
    if not re.fullmatch(r'[a-z0-9]{8,16}', token):
        raise ValueError('Reset ID must be 8–16 lowercase letters/digits')
    return PREFIX + token, ARCHIVE + token


def sql(query, database='postgres'):
    # No password is copied from the PostgreSQL pod into this process or argv.
    return command(['kubectl', 'exec', '-i', '-n', 'commons', 'commons-postgresql-0', '--',
                    'sh', '-c', 'PGPASSWORD="$POSTGRES_POSTGRES_PASSWORD" exec psql -X -qAt -v ON_ERROR_STOP=1 -U postgres -d "$1"',
                    'farmer-reset', database], 'SET standard_conforming_strings=on;\n' + query)


def properties(database):
    query = """SELECT json_build_object('oid',d.oid::bigint,'owner',r.rolname,
      'encoding',pg_encoding_to_char(d.encoding),'collation',d.datcollate,
      'ctype',d.datctype,'provider',d.datlocprovider,'icuLocale',d.daticulocale,
      'tablespace',t.spcname,'connectionLimit',d.datconnlimit,
      'acl',(SELECT coalesce(json_agg(x ORDER BY grantee,privilege_type,is_grantable),'[]') FROM
        (SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END grantee,
          a.privilege_type,a.is_grantable FROM aclexplode(coalesce(d.datacl,acldefault('d',d.datdba)))a)x),
      'settings',(SELECT coalesce(json_agg(x ORDER BY role_name,setting),'[]') FROM
        (SELECT CASE WHEN s.setrole=0 THEN '' ELSE pg_get_userbyid(s.setrole) END role_name,
         unnest(s.setconfig) setting FROM pg_db_role_setting s WHERE s.setdatabase=d.oid)x))
      FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba JOIN pg_tablespace t ON t.oid=d.dattablespace
      WHERE d.datname=""" + literal(database)
    raw = sql(query).strip()
    if not raw:
        raise ValueError('Expected reset database is absent')
    return json.loads(raw)


def creation_sql(candidate, original):
    if not candidate.startswith(PREFIX):
        raise ValueError('Only a Farmer reset candidate may be created')
    provider = {'c': 'libc', 'i': 'icu'}.get(original['provider'])
    if not provider:
        raise ValueError('Unsupported database locale provider')
    text = (f'CREATE DATABASE {ident(candidate)} WITH TEMPLATE template0 OWNER {ident(original["owner"])} '
            f'ENCODING {literal(original["encoding"])} LOCALE_PROVIDER {provider} '
            f'LC_COLLATE {literal(original["collation"])} LC_CTYPE {literal(original["ctype"])} '
            f'TABLESPACE {ident(original["tablespace"])} CONNECTION LIMIT {int(original["connectionLimit"])}')
    if provider == 'icu':
        text += ' ICU_LOCALE ' + literal(original['icuLocale'])
    statements = [text + ';', f'REVOKE ALL ON DATABASE {ident(candidate)} FROM PUBLIC;',
                  f'REVOKE ALL ON DATABASE {ident(candidate)} FROM {ident(original["owner"])};']
    for grant in original['acl']:
        if grant['privilege_type'] not in ('CREATE', 'CONNECT', 'TEMPORARY'):
            raise ValueError('Unexpected database grant')
        role = 'PUBLIC' if grant['grantee'] == 'PUBLIC' else ident(grant['grantee'])
        statements.append(f'GRANT {grant["privilege_type"]} ON DATABASE {ident(candidate)} TO {role}' +
                          (' WITH GRANT OPTION' if grant['is_grantable'] else '') + ';')
    for setting in original['settings']:
        key, value = setting['setting'].split('=', 1)
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_.]*', key):
            raise ValueError('Unexpected database setting')
        role = ' FOR ROLE ' + ident(setting['role_name']) if setting['role_name'] else ''
        statements.append(f'ALTER DATABASE {ident(candidate)}{role} SET {key} TO {literal(value)};'
                          if not role else f'ALTER ROLE {ident(setting["role_name"])} IN DATABASE {ident(candidate)} SET {key} TO {literal(value)};')
    return '\n'.join(statements) + '\n'


def schema_ready(database):
    # Check all expected tables/columns, not just whichever ones happen to exist.
    query = """SELECT json_build_object('coordinates',count(*),'compatible',count(*) FILTER
      (WHERE data_type IN ('real','double precision')),'document',
      (SELECT count(*) FROM information_schema.columns WHERE table_schema='public'
       AND table_name='g2p_register_document_history' AND column_name='event_type'
       AND data_type IN ('text','character varying') AND is_nullable='NO'))
      FROM information_schema.columns WHERE table_schema='public'
      AND table_name ~ '^g2p_(register_|register_history_|intake_form_)(farmers|households|household_members|lands)$'
      AND column_name IN ('latitude','longitude','altitude')"""
    result = json.loads(sql(query, database))
    if result != {'coordinates': 36, 'compatible': 36, 'document': 1}:
        raise ValueError('Candidate schema is incompatible with rc.544')


def fingerprint(database):
    tables = json.loads(sql("SELECT coalesce(json_agg(tablename ORDER BY tablename),'[]') FROM pg_tables WHERE schemaname='public'", database))
    result = {}
    for table in tables:
        # Small clean seed DB only; never fingerprint the million-row old register.
        raw = sql(f"SELECT json_build_object('rows',count(*),'hash',md5(coalesce(string_agg(h,'' ORDER BY h),''))) FROM (SELECT md5(to_jsonb(t)::text) h FROM public.{ident(table)} t)s", database)
        result[table] = json.loads(raw)
    if 'g2p_register_farmers' not in result:
        raise ValueError('Expected Farmer schema is absent')
    pattern = re.compile(r'^g2p_(register|register_history|intake_form)_(farmers|households|household_members|lands|livestocks|farm_inputs|membership_details|scores)$')
    if any(value['rows'] for table, value in result.items() if pattern.fullmatch(table) or table == 'g2p_register_document_history'):
        raise ValueError('Reset candidate must contain metadata only; business records are not empty')
    # Empty tables have no row hash to reveal a changed schema. Bind column,
    # constraint and index definitions as well as every metadata row.
    result['_schema'] = json.loads(sql("""SELECT json_build_object(
      'columns',(SELECT json_agg(x ORDER BY table_name,ordinal_position) FROM
       (SELECT table_name,column_name,ordinal_position,data_type,udt_name,is_nullable,column_default
        FROM information_schema.columns WHERE table_schema='public')x),
      'constraints',(SELECT json_agg(x ORDER BY relname,conname) FROM
       (SELECT c.relname,k.conname,pg_get_constraintdef(k.oid) definition FROM pg_constraint k
        JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public')x),
      'indexes',(SELECT json_agg(x ORDER BY tablename,indexname) FROM
       (SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public')x))""", database))
    return result


def paused(workloads):
    required = {f'farmer-registry-{suffix}' for suffix in ('staff-portal-api', 'partner-api', 'celery-worker', 'celery-beat-producer')}
    required.update(f'farmer-connector-{suffix}' for suffix in ('api', 'worker', 'beat'))
    present = {item['metadata']['name'] for item in workloads if item['kind'] == 'Deployment'}
    if not required <= present:
        raise ValueError('Expected Farmer writer inventory is incomplete')
    for item in workloads:
        name, kind = item['metadata']['name'], item['kind']
        if kind == 'Deployment' and name.startswith(('farmer-registry-', 'farmer-connector-')):
            # UI/ID generator do not write Registry business data.
            if name.endswith(('-ui', '-ui-pub', '-id-generator')):
                continue
            if item['spec'].get('replicas', 1) or item.get('status', {}).get('replicas', 0):
                raise ValueError('Farmer writer/connector replicas must be fully stopped')
        if kind == 'CronJob' and name.startswith('farmer-') and item['spec'].get('suspend') is not True:
            raise ValueError('Farmer CronJobs must be suspended')
        if kind == 'Job' and name.startswith('farmer-') and item.get('status', {}).get('active', 0):
            raise ValueError('Farmer Jobs are still active')


def swap_sql(candidate, archive, old_oid, candidate_oid):
    if not candidate.startswith(PREFIX) or archive != candidate.replace(PREFIX, ARCHIVE, 1):
        raise ValueError('Database swap names are outside Farmer staging')
    if type(old_oid) is not int or type(candidate_oid) is not int or old_oid == candidate_oid:
        raise ValueError('Distinct measured database OIDs required')
    # Renames are atomic. If the exchange fails, both databases stay inaccessible
    # and maintenance remains active; there is no automatic writer restart.
    return f"""SELECT pg_advisory_lock(724196309);
DO $$ BEGIN
 IF (SELECT oid FROM pg_database WHERE datname='{DATABASE}') IS DISTINCT FROM {old_oid}
 OR (SELECT oid FROM pg_database WHERE datname={literal(candidate)}) IS DISTINCT FROM {candidate_oid}
 OR EXISTS(SELECT FROM pg_database WHERE datname={literal(archive)}) THEN
 RAISE EXCEPTION 'Reset database identity changed'; END IF;
END $$;
ALTER DATABASE {ident(DATABASE)} WITH ALLOW_CONNECTIONS false;
ALTER DATABASE {ident(candidate)} WITH ALLOW_CONNECTIONS false;
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datid IN ({old_oid},{candidate_oid});
BEGIN;
ALTER DATABASE {ident(DATABASE)} RENAME TO {ident(archive)};
ALTER DATABASE {ident(candidate)} RENAME TO {ident(DATABASE)};
ALTER DATABASE {ident(DATABASE)} WITH ALLOW_CONNECTIONS true;
COMMIT;
SELECT pg_advisory_unlock(724196309);
"""


def promoted(record):
    sha = record.get('sourceCommit', '')
    implementation = record.get('implementationCommit', '')
    if not re.fullmatch('[0-9a-f]{40}', sha) or not re.fullmatch('[0-9a-f]{40}', implementation):
        raise ValueError('Promoted commit provenance required')
    remote = 'https://github.com/Centre-for-Open-Societal-Systems/farmer-registry.git'
    refs = dict((ref, commit) for commit, ref in (line.split() for line in command(['git', 'ls-remote', remote, 'refs/heads/develop', 'refs/heads/staging']).splitlines()))
    if refs.get('refs/heads/staging') != sha or command(['git', 'rev-parse', 'HEAD']).strip() != sha:
        raise ValueError('Reset requires the current promoted COSS staging checkout')
    for target in (sha, refs['refs/heads/develop']):
        command(['git', 'merge-base', '--is-ancestor', implementation, target])
    command(['git', 'diff', '--exit-code', implementation, sha, '--',
             'ci', 'helm', 'scripts', 'integrations', 'docker', 'farmer-extension', 'tests/runtime'])
    if record.get('deliveryHash') != delivery_hash():
        raise ValueError('Reset code changed after rehearsal')


def exchange_guard(record, plan, sealed, now=None):
    now = now or datetime.now(timezone.utc)
    if record.get('environment') != 'staging' or record.get('database') != DATABASE:
        raise ValueError('Only Farmer staging can be reset')
    if any(record.get('checks', {}).get(key) is not True for key in CHECKS):
        raise ValueError('Reset prerequisites are incomplete')
    for key, maximum in [('verifiedAt', timedelta(hours=24)), ('finalBackupAt', timedelta(hours=1))]:
        when = datetime.fromisoformat(record[key].replace('Z', '+00:00'))
        if when.tzinfo is None or not timedelta(0) <= now - when <= maximum:
            raise ValueError('Fresh reset rehearsal/final backups required')
    if record.get('planHash') != plan or record.get('sealedHash') != sealed:
        raise ValueError('Reset candidate changed after review')
    for key in ('registry', 'connector'):
        backup = record.get('backups', {}).get(key, {})
        if not re.fullmatch('[0-9a-f]{64}', backup.get('sha256', '')) or digest(backup['path']) != backup['sha256']:
            raise ValueError('Final backup integrity failed')


def render_jobs(manifest, candidate, images, token):
    """Reuse the reviewed chart's environment/Secrets; never run live shared hooks."""
    names(token)
    if candidate != PREFIX + token:
        raise ValueError('Unexpected candidate database')
    api = next(d for d in manifest if d.get('kind') == 'Deployment' and d['metadata']['name'] == 'farmer-registry-staff-portal-api')
    seed = next(d for d in manifest if d.get('kind') == 'Job' and d['metadata']['name'] == 'farmer-registry-db-seed')
    output = {}
    for stage, source, component in [('migrate', api, 'staff-api'), ('metadata', seed, 'db-seed')]:
        if source['metadata'].get('namespace', 'far') != 'far':
            raise ValueError('Reset Job source crosses environment')
        spec = copy.deepcopy(source['spec']['template']['spec'])
        container = next(c for c in spec['containers'] if c['name'] == ('staff-portal-api' if stage == 'migrate' else 'db-seed'))
        if container.get('envFrom') or spec.get('initContainers'):
            raise ValueError('Review hidden environment/init containers before reset')
        image = images[component]
        expected = r'\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com/openg2p/farmer-registry/' + component + r':[a-f0-9]{12}@sha256:[a-f0-9]{64}'
        if not re.fullmatch(expected, image):
            raise ValueError('Exact accepted image digest required')
        container['image'] = image
        env = container.setdefault('env', [])
        if len({e['name'] for e in env}) != len(env):
            raise ValueError('Duplicate reset Job environment')
        def set_env(name, value):
            env[:] = [e for e in env if e['name'] != name]
            env.append({'name': name, 'value': value})
        target = 'REGISTRY_STAFF_PORTAL_API_DB_DBNAME' if stage == 'migrate' else 'PGDATABASE'
        if next((e.get('value') for e in env if e['name'] == target), None) != DATABASE:
            raise ValueError('Reset Job source does not reference Farmer staging')
        set_env(target, candidate)
        for key in ('livenessProbe', 'readinessProbe', 'startupProbe', 'args', 'ports'):
            container.pop(key, None)
        if stage == 'migrate':
            env[:] = [e for e in env if e['name'].startswith('REGISTRY_STAFF_PORTAL_API_DB_')]
            set_env('REGISTRY_STAFF_PORTAL_API_AUDIT_ENABLED', 'false')
            container['command'] = ['python3', '-m', 'openg2p_registry_staff_api.main', 'migrate']
        else:
            # rc.544's seed Job has legacy direct-MDS DB variables. Do not give
            # the isolated metadata Job credentials to shared databases.
            env[:] = [e for e in env if not e['name'].startswith(('MD_PG', 'MDS_PG', 'AWE_', 'MINIO_'))]
            for flag in ('LOAD_GEO_DATA', 'LOAD_SAMPLE_DATA', 'LOAD_IMAGES', 'AWE_DB_SEED_ENABLED', 'SYNC_GEO_WIDGETS', 'LOAD_TEMPLATES'):
                set_env(flag, 'false')
            container['command'] = ['python3', '/seed/coss_seed.py']
        spec.update(containers=[container], restartPolicy='Never', automountServiceAccountToken=False)
        output[stage] = {'apiVersion': 'batch/v1', 'kind': 'Job',
                         'metadata': {'name': 'farmer-reset-' + token + '-' + stage, 'namespace': 'far'},
                         'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': 600,
                                  'template': {'metadata': {'annotations': {'sidecar.istio.io/inject': 'false'}}, 'spec': spec}}}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inventory', 'create', 'render-jobs', 'seal', 'exchange'))
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--reset-id')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--images', type=Path)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    validate_cluster('staging', os.environ.get('KUBECONFIG_CREDENTIAL'),
                     json.loads(command(['kubectl', 'config', 'view', '--minify', '-o', 'json'])))
    directory = args.directory.resolve()
    if args.action == 'inventory':
        candidate, archive = names(args.reset_id or '')
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        status = json.loads(command(['helm', 'status', 'farmer-registry', '-n', 'far', '-o', 'json']))
        values = json.loads(command(['helm', 'get', 'values', 'farmer-registry', '-n', 'far', '-o', 'json']))
        validate_release('staging', status, values)
        write(directory / 'plan.json', {'environment': 'staging', 'database': DATABASE, 'candidate': candidate,
                                      'archive': archive, 'resetId': args.reset_id,
                                      'original': properties(DATABASE), 'helmRevision': status['version']})
        write(directory / 'evidence.template.json', {
            'environment': 'staging', 'database': DATABASE, 'sourceCommit': '',
            'implementationCommit': '', 'deliveryHash': delivery_hash(),
            'verifiedAt': '', 'finalBackupAt': '', 'planHash': digest(directory / 'plan.json'),
            'sealedHash': '', 'checks': dict.fromkeys(CHECKS, False),
            'backups': {key: {'path': '', 'sha256': ''} for key in ('registry', 'connector')}})
    else:
        plan = json.loads((directory / 'plan.json').read_text())
        candidate, archive = names(plan['resetId'])
        if plan['environment'] != 'staging' or plan['database'] != DATABASE or (plan['candidate'], plan['archive']) != (candidate, archive):
            raise ValueError('Reset plan crosses environment')
        if args.action == 'create':
            record = json.loads(args.evidence.read_text())
            if record.get('checks', {}).get('resetAuthorized') is not True:
                raise ValueError('Explicit reviewed reset authorization required')
            promoted(record)
            if properties(DATABASE) != plan['original']:
                raise ValueError('Database baseline changed')
            statement = creation_sql(candidate, plan['original'])
            write(directory / 'create.sql', statement)
            sql(statement)
            sql('CREATE EXTENSION IF NOT EXISTS pg_trgm;', candidate)
        elif args.action == 'render-jobs':
            manifest = [d for d in yaml.safe_load_all(args.manifest.read_text()) if d]
            for stage, job in render_jobs(manifest, candidate, json.loads(args.images.read_text()), plan['resetId']).items():
                write(directory / (stage + '.json'), job)
        elif args.action == 'seal':
            current = properties(candidate)
            if any(current[key] != plan['original'][key] for key in PROPERTIES):
                raise ValueError('Candidate database permissions/settings differ from baseline')
            schema_ready(candidate)
            write(directory / 'sealed.json', {'candidate': current, 'tables': fingerprint(candidate)})
        else:
            record = json.loads(args.evidence.read_text())
            exchange_guard(record, digest(directory / 'plan.json'), digest(directory / 'sealed.json'))
            promoted(record)
            status = json.loads(command(['helm', 'status', 'farmer-registry', '-n', 'far', '-o', 'json']))
            if status.get('version') != plan['helmRevision'] or status.get('info', {}).get('status') != 'deployed':
                raise ValueError('Registry release changed after preparation')
            workloads = json.loads(command(['kubectl', 'get', 'deployments,cronjobs,jobs', '-n', 'far', '-o', 'json']))['items']
            paused(workloads)
            sealed = json.loads((directory / 'sealed.json').read_text())
            if properties(DATABASE) != plan['original'] or properties(candidate) != sealed['candidate']:
                raise ValueError('Reset database identity/settings changed')
            schema_ready(candidate)
            if fingerprint(candidate) != sealed['tables']:
                raise ValueError('Candidate rows changed after rehearsal')
            statement = swap_sql(candidate, archive, plan['original']['oid'], sealed['candidate']['oid'])
            write(directory / 'exchange.sql', statement)
            sql(statement)
            if properties(DATABASE)['oid'] != sealed['candidate']['oid']:
                raise ValueError('Unexpected post-exchange database identity')
            write(directory / 'exchanged.json', {'database': DATABASE, 'archive': archive,
                                               'at': datetime.now(timezone.utc).isoformat(),
                                               'candidateOid': sealed['candidate']['oid']})
    print(json.dumps({'action': args.action, 'environment': 'staging', 'directory': str(directory), 'status': 'completed'}))


if __name__ == '__main__':
    os.umask(0o077)
    try:
        main()
    except Exception:
        print('FAIL: Farmer staging reset stopped; private inputs/output withheld. Keep maintenance active after any exchange attempt.', file=sys.stderr)
        raise SystemExit(1)
