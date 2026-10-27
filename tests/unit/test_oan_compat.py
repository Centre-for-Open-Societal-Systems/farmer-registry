"""Compatibility edits must preserve all unlisted candidate configuration."""
import copy
import io
from pathlib import Path
import sys

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ci/deploy'))
import oan_compat


def fixture():
    before = [{'kind': 'Deployment', 'metadata': {'name': 'farmer-registry-staff-portal-api'},
               'spec': {'template': {'spec': {
                   'containers': [{'name': 'api', 'image': 'kept:old', 'env': [
                       {'name': 'PASSWORD', 'valueFrom': {'secretKeyRef': {'name': 'kept', 'key': 'key'}}}]}],
                   'initContainers': [{'name': 'postgres-checker', 'image': 'kept:init', 'env': [
                       {'name': 'PASSWORD', 'valueFrom': {'secretKeyRef': {'name': 'kept', 'key': 'key'}}}]}]}}}}]
    candidate = copy.deepcopy(before)
    for container in candidate[0]['spec']['template']['spec'].values():
        container[0]['env'].append({'name': 'COMMON_DB_HOSTNAME', 'value': 'packaged-default'})
    values = {'registry': {'staffApi': {'envVars': {'COMMON_DB_HOSTNAME': None},
                                       'envVarsFrom': {'COMMON_DB_HOSTNAME': None}}}}
    return before, candidate, values


def test_only_explicitly_suppressed_default_is_removed_from_app_and_init():
    before, candidate, values = fixture()
    original = copy.deepcopy(candidate)
    result = oan_compat.render(candidate, values)
    assert result == before
    assert candidate == original


@pytest.mark.parametrize('component', list(oan_compat.OMITTABLE))
def test_reviewed_omissions_for_every_app_and_init_pair(component):
    before, candidate, _ = fixture()
    suffix, names = oan_compat.OMITTABLE[component]
    before[0]['metadata']['name'] = candidate[0]['metadata']['name'] = 'farmer-registry-' + suffix
    for containers in candidate[0]['spec']['template']['spec'].values():
        containers[0]['env'] = copy.deepcopy(before[0]['spec']['template']['spec']['containers'][0]['env']) + [
            {'name': name, 'value': 'packaged-default'} for name in sorted(names)]
    values = {'registry': {component: {field: {name: None for name in names} for field in ('envVars', 'envVarsFrom')}}}
    assert oan_compat.render(candidate, values) == before


@pytest.mark.parametrize('field,value', [('envVars', 'configured'), ('envVarsFrom', {'secretKeyRef': {'name': 'keep', 'key': 'key'}})])
def test_literal_or_secret_reference_in_either_map_prevents_omission(field, value):
    _, candidate, values = fixture()
    values['registry']['staffApi'][field]['COMMON_DB_HOSTNAME'] = value
    assert oan_compat.render(candidate, values) == candidate


def test_null_in_one_map_does_not_authorize_omission():
    _, candidate, values = fixture()
    values['registry']['staffApi']['envVarsFrom'].clear()
    assert oan_compat.render(candidate, values) == candidate


def test_duplicate_environment_is_rejected_before_filtering():
    _, candidate, values = fixture()
    candidate[0]['spec']['template']['spec']['containers'][0]['env'].append(
        {'name': 'COMMON_DB_HOSTNAME', 'value': 'second-default'})
    with pytest.raises(ValueError, match='Duplicate'):
        oan_compat.render(candidate, values)


def test_unlisted_defaults_are_kept_even_when_nulled():
    before, candidate, values = fixture()
    unreviewed = {'name': 'UNREVIEWED', 'value': 'new'}
    candidate[0]['spec']['template']['spec']['containers'][0]['env'].append(unreviewed)
    for field in ('envVars', 'envVarsFrom'):
        values['registry']['staffApi'][field]['UNREVIEWED'] = None
    result = oan_compat.render(candidate, values)
    assert unreviewed in result[0]['spec']['template']['spec']['containers'][0]['env']
    assert result != before


@pytest.mark.parametrize('mutation', ['command', 'secret', 'route', 'pvc', 'selector'])
def test_renderer_changes_nothing_but_the_listed_defaults(mutation):
    _, candidate, values = fixture()
    if mutation == 'command':
        candidate[0]['spec']['template']['spec']['containers'][0]['command'] = ['changed']
    elif mutation == 'secret':
        candidate[0]['spec']['template']['spec']['initContainers'][0]['env'][0]['valueFrom']['secretKeyRef']['key'] = 'changed'
    elif mutation == 'selector':
        candidate[0]['spec']['selector'] = {'matchLabels': {'changed': 'true'}}
    else:
        kind = 'VirtualService' if mutation == 'route' else 'PersistentVolumeClaim'
        candidate.append({'kind': kind, 'metadata': {'name': 'kept'}, 'spec': {'setting': 'changed'}})
    expected = copy.deepcopy(candidate)
    for containers in expected[0]['spec']['template']['spec'].values():
        containers[0]['env'] = [item for item in containers[0]['env'] if item['name'] != 'COMMON_DB_HOSTNAME']
    assert oan_compat.render(candidate, values) == expected


def test_reporting_command_is_byte_for_byte_unchanged_in_utf8():
    _, candidate, values = fixture()
    command = "echo 'refresh — nothing to do'\n"
    cron = {'kind': 'CronJob', 'metadata': {'name': 'farmer-registry-fr-reporting-views-refresh'},
            'spec': {'jobTemplate': {'spec': {'template': {'spec': {'containers': [
                {'name': 'refresh', 'command': ['sh', '-c', command]}]}}}}}}
    candidate.append(cron)
    assert oan_compat.render(candidate, values)[-1] == cron


def test_main_verifies_package_and_keeps_jobs_unless_chart_only(tmp_path, monkeypatch, capsys):
    before, candidate, values = fixture()
    candidate.append({'kind': 'Job', 'metadata': {'name': 'initialization'}})
    path = tmp_path / 'values.yaml'
    path.write_text(yaml.safe_dump(values), encoding='utf-8')
    for name, value in [('DELIVERY_ENVIRONMENT', 'dev'), ('HELM_NAMESPACE', 'farmer'),
                        ('HELM_RELEASE', 'farmer-registry'), ('OAN_VALUES_FILE', str(path)),
                        ('OAN_CHART_ARCHIVE', 'verified-archive')]:
        monkeypatch.setenv(name, value)
    calls = []
    def verify(path):
        calls.append(path)
        return {'version': '1.0.0-dev.16'}
    monkeypatch.setattr(oan_compat, 'verify', verify)
    for mode in ('false', 'true'):
        monkeypatch.setenv('OAN_CHART_ONLY', mode)
        monkeypatch.setattr(sys, 'stdin', io.StringIO(yaml.safe_dump_all(candidate)))
        oan_compat.main()
        result = list(yaml.safe_load_all(capsys.readouterr().out))
        assert len(result) == (1 if mode == 'true' else 2)
        assert result[0] == before[0]
    assert calls == ['verified-archive', 'verified-archive']
    monkeypatch.setenv('HELM_NAMESPACE', 'far')
    with pytest.raises(ValueError):
        oan_compat.main()
