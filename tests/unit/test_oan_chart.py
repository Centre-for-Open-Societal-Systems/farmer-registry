"""Fail-closed package, image and metadata-only cutover gates."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
from datetime import datetime, timedelta, timezone

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ci/deploy'))
import oan_chart
import cutover
import deployment


def archive(path, version=None):
    pin = oan_chart.profile()
    version = version or pin['platformVersion']
    chart = {'name': pin['name'], 'version': pin['version'], 'appVersion': pin['platformVersion'],
             'dependencies': [{'alias': 'registry', 'name': 'openg2p-registry',
                               'version': pin['platformVersion'], 'repository': 'https://openg2p.github.io/openg2p-helm'}]}
    with tarfile.open(path, 'w:gz') as target:
        for name, value in [('Chart.yaml', chart), ('charts/openg2p-registry/Chart.yaml',
                             {'name': 'openg2p-registry', 'version': version})]:
            data = yaml.safe_dump(value).encode()
            entry = tarfile.TarInfo(pin['name'] + '/' + name)
            entry.size = len(data)
            target.addfile(entry, io.BytesIO(data))
    return {**pin, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def test_archive_missing_corrupt_checksum_and_incompatible_child(tmp_path, monkeypatch):
    path = tmp_path / 'package.tgz'
    with pytest.raises(OSError):
        oan_chart.verify(path)
    pin = archive(path)
    monkeypatch.setattr(oan_chart, 'profile', lambda: pin)
    assert oan_chart.verify(path) == pin
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='checksum'):
        oan_chart.verify(path)
    pin = archive(path, 'wrong')
    with pytest.raises(ValueError, match='dependency'):
        oan_chart.verify(path)


def workload():
    return {'kind': 'Deployment', 'metadata': {'name': 'farmer-registry-staff-portal-api',
            'labels': {'helm.sh/chart': 'old'}}, 'spec': {'template': {'spec': {
            'containers': [{'name': 'api', 'image': 'example/api:installed', 'env': [{'name': 'A', 'value': '1'}]}],
            'initContainers': [{'name': 'init', 'image': 'example/init:installed', 'env': [
                {'name': 'PASSWORD', 'valueFrom': {'secretKeyRef': {'name': 'installed', 'key': 'password'}}}]}]}}}}


def test_cutover_allows_only_chart_label_and_environment_order():
    before = [workload()]
    after = copy.deepcopy(before)
    after[0]['metadata']['labels']['helm.sh/chart'] = 'openg2p-farmer-registry-1.0.0-dev.5'
    cutover.validate(before, after)
    deployment.pod(after[0])['initContainers'][0]['env'][0]['valueFrom']['secretKeyRef']['name'] = 'changed'
    with pytest.raises(ValueError, match='configuration'):
        cutover.validate(before, after)


@pytest.mark.parametrize('environment,namespace', [('staging', 'far'), ('dev', 'far'), ('prod', 'farmer')])
def test_cutover_rejects_wrong_environment_and_namespace(monkeypatch, environment, namespace):
    monkeypatch.setenv('DELIVERY_ENVIRONMENT', environment)
    monkeypatch.setenv('HELM_NAMESPACE', namespace)
    monkeypatch.setenv('HELM_RELEASE', 'farmer-registry')
    monkeypatch.setattr(sys, 'argv', ['cutover.py', 'filter'])
    with pytest.raises(ValueError, match='dev/farmer'):
        cutover.main()


def test_postrenderer_suppresses_jobs_but_keeps_configuration(monkeypatch, capsys):
    for name, value in [('DELIVERY_ENVIRONMENT', 'dev'), ('HELM_NAMESPACE', 'farmer'), ('HELM_RELEASE', 'farmer-registry')]:
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, 'argv', ['cutover.py', 'filter'])
    docs = [workload(), {'kind': 'Job', 'metadata': {'name': 'init'}},
            {'kind': 'ConfigMap', 'metadata': {'name': 'iam-payload'}}]
    monkeypatch.setattr(sys, 'stdin', io.StringIO(yaml.safe_dump_all(docs)))
    cutover.main()
    result = list(yaml.safe_load_all(capsys.readouterr().out))
    assert [d['kind'] for d in result] == ['Deployment', 'ConfigMap']


@pytest.mark.parametrize('action,status,accepted', [('adopted', 'failed', True), ('installed', 'failed', False),
                                                  ('installed', 'deployed', True)])
def test_adopted_chart_keeps_recovery_but_requires_deployed_completion(tmp_path, monkeypatch, action, status, accepted):
    for name, value in [('DELIVERY_ENVIRONMENT', 'dev'), ('HELM_NAMESPACE', 'farmer'), ('HELM_RELEASE', 'farmer-registry')]:
        monkeypatch.setenv(name, value)
    path = tmp_path / 'list.json'
    pin = oan_chart.profile()
    path.write_text(json.dumps([{'name': 'farmer-registry', 'namespace': 'farmer',
                                 'chart': pin['name'] + '-' + pin['version'], 'status': status}]))
    monkeypatch.setattr(sys, 'argv', ['cutover.py', action, str(path)])
    if accepted:
        cutover.main()
    else:
        with pytest.raises(ValueError):
            cutover.main()


@pytest.mark.parametrize('change', ['new-resource', 'new-env', 'image', 'job', 'cron-command'])
def test_cutover_rejects_nonmetadata_changes(change):
    before = [workload()]
    after = copy.deepcopy(before)
    if change == 'new-resource':
        after.append({'kind': 'PersistentVolumeClaim', 'metadata': {'name': 'unexpected'}})
    elif change == 'new-env':
        deployment.pod(after[0])['containers'][0]['env'].append({'name': 'ADDED', 'value': 'true'})
    elif change == 'image':
        deployment.pod(after[0])['containers'][0]['image'] = 'example/api:new'
    elif change == 'job':
        after.append({'kind': 'Job', 'metadata': {'name': 'initialization'}})
    else:
        before.append({'kind': 'CronJob', 'metadata': {'name': 'refresh'}, 'spec': {'command': '# correct encoding'}})
        after.append({'kind': 'CronJob', 'metadata': {'name': 'refresh'}, 'spec': {'command': '# changed encoding'}})
    with pytest.raises(ValueError):
        cutover.validate(before, after)


def test_dev_digest_set_pins_both_celery_seed_and_sanity():
    ecr = '123456789012.dkr.ecr.ap-south-1.amazonaws.com'
    tag = 'a' * 12
    images = {component: {'tag': tag, 'digest': 'sha256:' + 'b' * 64} for _, _, component in deployment.COMPONENTS.values()}
    values = {'global': {'registryHostname': 'farmer-registry.development.oanstaging.com'}}
    result = deployment.prepare(values, [workload()], ecr, tag, images=images)
    for component in deployment.COMPONENTS:
        assert result['registry'][component]['image']['tag'] == tag + '@sha256:' + 'b' * 64
        assert result['registry'][component]['image']['digest'] == ''
    assert result['analytics']['image']['tag'] == tag + '@sha256:' + 'b' * 64


def test_normal_guard_checks_init_environment_and_new_pvc():
    before = workload()
    after = copy.deepcopy(before)
    deployment.pod(after)['initContainers'][0]['env'][0]['valueFrom']['secretKeyRef']['name'] = 'changed'
    with pytest.raises(ValueError, match='environment/Secret'):
        deployment.validate([before], [after], '123456789012.dkr.ecr.ap-south-1.amazonaws.com', 'a' * 12)


@pytest.mark.parametrize('violation', ['none', 'active-job', 'unfinished-job', 'stale', 'revision', 'checksum', 'wrong-commit'])
def test_cutover_backup_freshness_revision_restore_and_active_job_gates(tmp_path, violation):
    commit = 'a' * 40
    manifest = []
    for kind, suffix, component in deployment.COMPONENTS.values():
        if kind == 'Deployment':
            doc = workload()
            doc['metadata']['name'] = 'farmer-registry-' + suffix
            deployment.pod(doc)['containers'][0]['image'] = 'example/' + component + ':' + commit[:12]
            manifest.append(doc)
    status = {'name': 'farmer-registry', 'namespace': 'farmer', 'version': 39, 'info': {'status': 'deployed'}}
    values = {'private': 'not-published'}
    payloads = {'release.json': json.dumps(status).encode(), 'values.json': json.dumps(values).encode(),
                'manifest.yaml': yaml.safe_dump_all(manifest).encode(), 'hooks.yaml': b'',
                'registry.dump': b'synthetic registry backup', 'connector.dump': b'synthetic connector backup'}
    for name, payload in payloads.items():
        (tmp_path / name).write_bytes(payload)
    evidence = {'verifiedAt': datetime.now(timezone.utc).isoformat(), 'helmRevision': 39,
                'release': 'farmer-registry', 'namespace': 'farmer', 'applicationCommit': commit,
                'restoreVerified': True, 'reviewedJobRemovals': [],
                'sha256': {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}}
    jobs = {'items': []}
    if violation in ('active-job', 'unfinished-job'):
        jobs['items'].append({'metadata': {'name': 'farmer-registry-postgres-init'},
                              'status': {'active': 1} if violation == 'active-job' else {}})
    elif violation == 'stale':
        evidence['verifiedAt'] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    elif violation == 'revision':
        evidence['helmRevision'] = 38
    elif violation == 'checksum':
        (tmp_path / 'registry.dump').write_bytes(b'changed')
    elif violation == 'wrong-commit':
        evidence['applicationCommit'] = 'b' * 40
    (tmp_path / 'cutover-evidence.json').write_text(json.dumps(evidence), encoding='utf-8')
    if violation == 'none':
        cutover.backup_gate(tmp_path, status, values, manifest, jobs)
    else:
        with pytest.raises(ValueError):
            cutover.backup_gate(tmp_path, status, values, manifest, jobs)


def test_deployment_requires_explicit_acceptance_for_the_exact_environment(monkeypatch):
    original = oan_chart.profile()
    for pin, environment in ((original,'dev'),({**original,'promotionReady':True},'staging')):
        monkeypatch.setattr(oan_chart,'profile',lambda pin=pin:pin)
        with pytest.raises(ValueError,match='Deployment blocked'):
            oan_chart.require_deployable(environment)
    monkeypatch.setattr(oan_chart,'profile',lambda:{**original,'promotionReady':True})
    oan_chart.require_deployable('dev')
