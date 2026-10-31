"""Fail-closed boundaries for the explicit destructive staging test-data reset."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('staging_reset', ROOT / 'scripts/operations/staging/reset_registry.py')
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)


def test_swap_archives_both_databases_and_is_atomic():
    candidate, archive = reset.names('20261016')
    sql = reset.swap_sql(candidate, archive, 123, 456)
    assert 'DROP ' not in sql
    assert sql.index('ALLOW_CONNECTIONS false') < sql.index('pg_terminate_backend') < sql.index('BEGIN;')
    assert sql.index('BEGIN;') < sql.index('RENAME TO') < sql.index('ALLOW_CONNECTIONS true') < sql.index('COMMIT;')
    assert 'farmer_registry_far_archive_20261016' in sql
    assert 'Reset database identity changed' in sql


@pytest.mark.parametrize('token', ['dev', '../staging', 'abcdefgh;DROP', 'x'*17, 'ABCDEF12'])
def test_reset_identifier_cannot_inject_sql_or_target_dev(token):
    with pytest.raises(ValueError):
        reset.names(token)


def test_swap_refuses_cross_environment_or_reused_database():
    for values in [('farmer_registry', 'farmer_registry_old', 1, 2),
                   ('farmer_registry_far_reset_20261016', 'other', 1, 2),
                   (*reset.names('20261016'), 1, 1),
                   (*reset.names('20261016'), True, 2)]:
        with pytest.raises(ValueError):
            reset.swap_sql(*values)


@pytest.fixture
def evidence(tmp_path):
    dump = tmp_path / 'dump'
    dump.write_bytes(b'isolated-synthetic-dump')
    now = datetime(2026, 10, 16, 8, tzinfo=timezone.utc)
    return {'environment': 'staging', 'database': reset.DATABASE,
            'verifiedAt': now.isoformat(), 'finalBackupAt': now.isoformat(),
            'planHash': 'plan', 'sealedHash': 'sealed',
            'checks': dict.fromkeys(reset.CHECKS, True),
            'backups': {key: {'path': str(dump), 'sha256': reset.digest(dump)} for key in ('registry', 'connector')}}, now


@pytest.mark.parametrize('check', reset.CHECKS)
def test_each_reset_prerequisite_is_mandatory(evidence, check):
    record, now = evidence
    reset.exchange_guard(record, 'plan', 'sealed', now)
    record['checks'][check] = False
    with pytest.raises(ValueError):
        reset.exchange_guard(record, 'plan', 'sealed', now)


@pytest.mark.parametrize('field,value', [('environment', 'dev'), ('database', 'master_data'),
    ('verifiedAt', '2026-10-14T08:00:00Z'), ('finalBackupAt', '2026-10-16T06:59:00Z'),
    ('finalBackupAt', '2026-10-16T09:00:00Z'), ('finalBackupAt', '2026-10-16T08:00:00'),
    ('planHash', 'other'), ('sealedHash', 'other')])
def test_stale_backup_plan_drift_and_other_databases_cannot_authorize_reset(evidence, field, value):
    record, now = evidence
    record[field] = value
    with pytest.raises(ValueError):
        reset.exchange_guard(record, 'plan', 'sealed', now)


def test_changed_backup_cannot_authorize_reset(evidence):
    record, now = evidence
    Path(record['backups']['registry']['path']).write_bytes(b'changed')
    with pytest.raises(ValueError):
        reset.exchange_guard(record, 'plan', 'sealed', now)


def test_candidate_seal_rejects_nonempty_register_and_requires_farmer_schema(monkeypatch):
    def query(statement, database):
        if 'FROM pg_tables' in statement:
            return json.dumps(['g2p_register_farmers', 'g2p_register_definitions'])
        return json.dumps({'rows': 0 if '"g2p_register_farmers"' in statement else 8, 'hash': 'abc'})
    monkeypatch.setattr(reset, 'sql', query)
    assert reset.fingerprint(reset.PREFIX + '20261016')['g2p_register_farmers']['rows'] == 0
    monkeypatch.setattr(reset, 'sql', lambda q, d: json.dumps(['g2p_register_farmers']) if 'FROM pg_tables' in q else json.dumps({'rows': 1, 'hash': 'abc'}))
    with pytest.raises(ValueError, match='metadata only'):
        reset.fingerprint(reset.PREFIX + '20261016')


@pytest.mark.parametrize('kind,spec,status', [('Deployment', {'replicas': 1}, {}),
    ('Deployment', {'replicas': 0}, {'replicas': 1}), ('CronJob', {}, {}), ('Job', {}, {'active': 1})])
def test_live_or_terminating_writers_block_exchange(kind, spec, status):
    workloads = stopped_workloads()
    if kind == 'Deployment':
        workloads = [d for d in workloads if d['metadata']['name'] != 'farmer-registry-celery-worker']
    workloads.append({'kind': kind, 'metadata': {'name': 'farmer-registry-celery-worker'}, 'spec': spec, 'status': status})
    with pytest.raises(ValueError, match='fully stopped|suspended|still active'):
        reset.paused(workloads)


def stopped_workloads():
    names = ['farmer-registry-' + s for s in ('staff-portal-api', 'partner-api', 'celery-worker', 'celery-beat-producer')]
    names += ['farmer-connector-' + s for s in ('api', 'worker', 'beat')]
    return [{'kind': 'Deployment', 'metadata': {'name': name}, 'spec': {'replicas': 0}, 'status': {'replicas': 0}} for name in names]


def test_stopped_expected_writers_pass_but_missing_inventory_does_not():
    workloads = stopped_workloads()
    reset.paused(workloads)
    with pytest.raises(ValueError, match='incomplete'):
        reset.paused(workloads[:-1])


def manifest():
    def pod(name, dbkey):
        return {'metadata': {'name': name, 'namespace': 'far'}, 'spec': {'template': {'spec': {
            'containers': [{'name': 'staff-portal-api' if 'staff-portal-api' in name else 'db-seed',
                'image': 'old', 'args': ['old'], 'readinessProbe': {'httpGet': {'path': '/'}},
                'env': [{'name': dbkey, 'value': reset.DATABASE},
                        {'name': 'PGPASSWORD', 'valueFrom': {'secretKeyRef': {'name': 'retained', 'key': 'password'}}}]}]}}}}
    api, seed = pod('farmer-registry-staff-portal-api', 'REGISTRY_STAFF_PORTAL_API_DB_DBNAME'), pod('farmer-registry-db-seed', 'PGDATABASE')
    api['kind'], seed['kind'] = 'Deployment', 'Job'
    return [api, seed]


def images():
    root = '379220350808.dkr.ecr.ap-south-1.amazonaws.com/openg2p/farmer-registry/'
    return {key: root + key + ':' + 'a'*12 + '@sha256:' + 'b'*64 for key in ('staff-api', 'db-seed')}


def test_reset_jobs_preserve_secrets_target_candidate_and_disable_shared_hooks():
    original = manifest()
    before = copy.deepcopy(original)
    jobs = reset.render_jobs(original, reset.PREFIX + '20261016', images(), '20261016')
    assert original == before
    for name, job in jobs.items():
        assert job['spec']['template']['metadata']['annotations']['sidecar.istio.io/inject'] == 'false'
        pod = job['spec']['template']['spec']
        c = pod['containers'][0]
        assert pod['automountServiceAccountToken'] is False
        assert len(pod['containers']) == 1
        assert 'readinessProbe' not in c and 'args' not in c
        env = {e['name']: e for e in c['env']}
        if name != 'migrate':
            assert env['PGPASSWORD']['valueFrom']['secretKeyRef']['name'] == 'retained'
            assert env['PGDATABASE']['value'] == reset.PREFIX + '20261016'
            for flag in ('LOAD_GEO_DATA', 'LOAD_SAMPLE_DATA', 'AWE_DB_SEED_ENABLED', 'LOAD_TEMPLATES'):
                assert env[flag]['value'] == 'false'
    assert set(jobs) == {'metadata', 'migrate'}
    assert jobs['metadata']['spec']['template']['spec']['containers'][0]['command'][-1] == '/seed/coss_seed.py'


def test_reset_jobs_refuse_dev_manifests_hidden_init_and_mutable_images():
    for mutation in ('namespace', 'database', 'init', 'image'):
        docs, selected = manifest(), images()
        if mutation == 'namespace': docs[0]['metadata']['namespace'] = 'farmer'
        if mutation == 'database': docs[0]['spec']['template']['spec']['containers'][0]['env'][0]['value'] = 'farmer_registry'
        if mutation == 'init': docs[0]['spec']['template']['spec']['initContainers'] = [{}]
        if mutation == 'image': selected['db-seed'] = 'latest'
        with pytest.raises(ValueError):
            reset.render_jobs(docs, reset.PREFIX + '20261016', selected, '20261016')


def test_source_must_already_be_promoted_through_develop(monkeypatch):
    commit, implementation = 'a'*40, 'b'*40
    record = {'sourceCommit': commit, 'implementationCommit': implementation, 'deliveryHash': 'hash'}
    calls = []
    def command(args):
        calls.append(args)
        if args[1] == 'ls-remote': return commit + '\trefs/heads/staging\n' + 'c'*40 + '\trefs/heads/develop\n'
        if args[1] == 'rev-parse': return commit
        if args[1] == 'merge-base': return ''
        if args[1] == 'diff': return ''
        raise AssertionError(args)
    monkeypatch.setattr(reset, 'command', command)
    monkeypatch.setattr(reset, 'delivery_hash', lambda: 'hash')
    reset.promoted(record)
    assert ['git', 'merge-base', '--is-ancestor', implementation, 'c'*40] in calls
    assert ['git', 'merge-base', '--is-ancestor', implementation, commit] in calls
    record['sourceCommit'] = 'd'*40
    with pytest.raises(ValueError): reset.promoted(record)


def test_probe_runs_only_readonly_script_with_database_secret_references():
    sys_path = str(ROOT / 'ci/deploy')
    import sys
    sys.path.insert(0, sys_path)
    import deployment
    doc = manifest()[0]
    c = doc['spec']['template']['spec']['containers'][0]
    c['env'].extend({'name': 'REGISTRY_STAFF_PORTAL_API_DB_' + key, 'valueFrom': {'secretKeyRef': {'name': 'db', 'key': key}}} for key in ('HOSTNAME', 'USERNAME', 'PASSWORD'))
    job = deployment.schema_probe(doc, images()['staff-api'])
    probe = job['spec']['template']['spec']
    assert job['spec']['template']['metadata']['annotations']['sidecar.istio.io/inject'] == 'false'
    assert probe['automountServiceAccountToken'] is False
    assert 'readonly=True' in probe['containers'][0]['command'][-1]
    assert 'migrate' not in probe['containers'][0]['command'][:2]
    assert all(e['name'].startswith('REGISTRY_STAFF_PORTAL_API_DB_') for e in probe['containers'][0]['env'])
    doc['metadata']['namespace'] = 'farmer'
    with pytest.raises(ValueError): deployment.schema_probe(doc, images()['staff-api'])
