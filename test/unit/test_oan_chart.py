"""Fail-closed package and image gates for the pinned OAN chart."""
import copy
import hashlib
import io
from pathlib import Path
import re
import sys
import tarfile

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ci/deploy'))
import oan_chart
import oan_compat
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
    # The version moves with reviewed pin pull requests (ci/deploy/bump_pin.py); the platform only with the images.
    assert re.fullmatch(r'1\.0\.0-dev\.\d+', pin['version'])
    assert pin['platformVersion'] in oan_compat.REVIEWED_PLATFORMS
    assert 'promotionReady' not in pin and 'freshDatabaseEpoch' not in pin


def test_deployment_requires_the_dev_pin_for_dev(monkeypatch):
    original = oan_chart.profile('dev')
    oan_chart.require_deployable('dev')
    monkeypatch.setattr(oan_chart, 'profile', lambda environment=None: {**original, 'environment': 'staging'})
    with pytest.raises(ValueError, match='Deployment blocked'):
        oan_chart.require_deployable('dev')


def test_staging_pin_is_the_dev_chart_made_for_staging():
    dev, staging = oan_chart.profile('dev'), oan_chart.profile('staging')
    assert (staging['environment'], staging['namespace'], staging['release']) == ('staging', 'farmer', 'farmer-registry')
    # Staging is pinned to oan-helm d7588ad (chart dev.20) and moves only by a reviewed change; dev follows
    # oan-helm main through pin pull requests. Same chart name; dev may run a newer reviewed platform first.
    assert staging['name'] == dev['name']
    assert {staging['platformVersion'], dev['platformVersion']} <= oan_compat.REVIEWED_PLATFORMS
    assert (staging['version'], staging['platformVersion']) == ('1.0.0-dev.20', '1.2.2-rc.614')
    assert staging['repository'].split('/')[-3] == staging['values']['commit']


def test_staging_is_accepted_and_every_other_environment_rejected():
    oan_chart.require_deployable('dev')
    oan_chart.require_deployable('staging')
    for other in ('staging-legacy', 'production', 'prod', '', 'Staging'):
        with pytest.raises(ValueError, match='Deployment blocked'):
            oan_chart.require_deployable(other)
    with pytest.raises(ValueError):
        oan_chart.profile('production')


def test_pin_environment_must_equal_the_requested_one(monkeypatch):
    original = oan_chart.profile('staging')
    monkeypatch.setattr(oan_chart, 'profile', lambda environment=None: {**original, 'environment': 'dev'})
    with pytest.raises(ValueError, match='Deployment blocked'):
        oan_chart.require_deployable('staging')


def test_profile_follows_the_delivery_environment_variable(monkeypatch):
    monkeypatch.setenv('DELIVERY_ENVIRONMENT', 'staging')
    assert oan_chart.profile()['environment'] == 'staging'
    monkeypatch.delenv('DELIVERY_ENVIRONMENT')
    assert oan_chart.profile()['environment'] == 'dev'


def test_staging_values_are_pinned_by_commit_and_checksum(monkeypatch):
    url, digest = oan_chart.values_url('staging')
    assert url.endswith('/' + oan_chart.profile('staging')['values']['commit'] + '/environments/staging/values/farmer.yaml')
    assert len(digest) == 64
    unpinned = {**oan_chart.profile('staging'), 'values': {'path': 'environments/staging/values/farmer.yaml', 'commit': '', 'sha256': ''}}
    monkeypatch.setattr(oan_chart, 'profile', lambda environment=None: unpinned)
    with pytest.raises(ValueError, match='not pinned'):
        oan_chart.values_url('staging')
    pinned = {**unpinned, 'values': {
        'path': 'environments/staging/values/farmer.yaml', 'commit': 'a' * 40, 'sha256': 'b' * 64}}
    monkeypatch.setattr(oan_chart, 'profile', lambda environment=None: pinned)
    url, digest = oan_chart.values_url('staging')
    assert url == 'https://raw.githubusercontent.com/Centre-for-Open-Societal-Systems/oan-helm/' + 'a' * 40 + '/environments/staging/values/farmer.yaml'
    assert digest == 'b' * 64
    pinned['values']['path'] = '../../etc/passwd'
    with pytest.raises(ValueError, match='not pinned'):
        oan_chart.values_url('staging')


def _running(tmp_path, version, chart='openg2p-farmer-registry'):
    path = tmp_path / 'running-chart.json'
    path.write_text('' if version is None else
                    '{"name": "farmer-registry", "chart": "%s", "version": "%s", "appVersion": "1.2.2-rc.625"}'
                    % (chart, version), encoding='utf-8')
    return path


def test_semver_orders_rc_after_dev_and_numbers_numerically():
    order = ['1.0.0-dev.2', '1.0.0-dev.20', '1.0.0-rc.9', '1.0.0-rc.882', '1.0.0', '1.0.1-dev.1']
    assert sorted(order, key=oan_chart._semver) == order
    with pytest.raises(ValueError):
        oan_chart._semver('latest')


def test_operator_path_never_installs_a_chart_older_than_staging_runs(tmp_path):
    pin = oan_chart.profile('staging')
    # Staging runs a promoted rc newer than the pin: the operator action stops and says why.
    with pytest.raises(ValueError, match='would downgrade') as blocked:
        oan_chart.require_current('staging', _running(tmp_path, '1.0.0-rc.99999'))
    assert pin['version'] in str(blocked.value) and '1.0.0-rc.99999' in str(blocked.value)
    # The release runs the pinned chart, or there is no release yet (first install): allowed.
    assert 'not older' in oan_chart.require_current('staging', _running(tmp_path, pin['version']))
    assert 'no staging release' in oan_chart.require_current('staging', _running(tmp_path, None))
    with pytest.raises(ValueError, match='runs chart'):
        oan_chart.require_current('staging', _running(tmp_path, pin['version'], chart='other-chart'))


def test_operator_scripts_check_the_running_chart_before_installing():
    root = Path(__file__).resolve().parents[2]
    for script in ('ci/deploy/deploy-rc.sh', 'ci/deploy/fresh-install-staging.sh'):
        text = (root / script).read_text(encoding='utf-8')
        check = text.index('guard require-current staging')
        assert text.index('helm get metadata "$HELM_RELEASE"') < check
        assert check < text.index('guard verify "$CHART"')
        # A metadata read that fails for any reason other than a missing release stops the run.
        assert "grep -q 'not found'" in text
