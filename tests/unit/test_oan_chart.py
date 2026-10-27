"""Fail-closed package and image gates for the pinned OAN chart."""
import copy
import hashlib
import io
from pathlib import Path
import sys
import tarfile

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ci/deploy'))
import oan_chart
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


def test_pin_is_the_deployed_dev_chart_without_promotion_flags():
    pin = oan_chart.profile()
    assert (pin['environment'], pin['namespace'], pin['release']) == ('dev', 'farmer', 'farmer-registry')
    assert pin['version'] == '1.0.0-dev.16' and pin['platformVersion'] == '1.2.2-rc.557'
    assert 'promotionReady' not in pin and 'freshDatabaseEpoch' not in pin


def test_deployment_requires_the_dev_pin_for_dev(monkeypatch):
    original = oan_chart.profile()
    oan_chart.require_deployable('dev')
    with pytest.raises(ValueError, match='Deployment blocked'):
        oan_chart.require_deployable('staging')
    monkeypatch.setattr(oan_chart, 'profile', lambda: {**original, 'environment': 'staging'})
    with pytest.raises(ValueError, match='Deployment blocked'):
        oan_chart.require_deployable('dev')
