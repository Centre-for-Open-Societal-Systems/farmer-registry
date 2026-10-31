"""Verify the approved archive without extracting or resolving dependencies."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tarfile

import yaml


# One pin file per environment. Dev keeps oan-chart.json; the others are oan-chart-<environment>.json.
ENVIRONMENTS = ('dev', 'staging')


def profile(environment=None):
    """The pin of the requested environment (default: DELIVERY_ENVIRONMENT, else dev)."""
    environment = environment or os.environ.get('DELIVERY_ENVIRONMENT') or 'dev'
    if environment not in ENVIRONMENTS:
        raise ValueError('No OAN chart pin for this environment')
    name = 'oan-chart.json' if environment == 'dev' else 'oan-chart-%s.json' % environment
    return json.loads(Path(__file__).with_name(name).read_text(encoding='utf-8'))


def verify(path, pin=None):
    pin = profile() if pin is None else pin
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != pin['sha256']:
        raise ValueError('OAN chart checksum mismatch')
    with tarfile.open(path, 'r:gz') as archive:
        def read(name):
            return yaml.safe_load(archive.extractfile(pin['name'] + '/' + name))
        chart = read('Chart.yaml')
        dependency = {'alias': 'registry', 'name': 'openg2p-registry',
                      'repository': 'https://openg2p.github.io/openg2p-helm',
                      'version': pin['platformVersion']}
        if (chart['name'], chart['version'], chart['appVersion'], chart['dependencies']) != (
                pin['name'], pin['version'], pin['platformVersion'], [dependency]):
            raise ValueError('Incompatible OAN chart/platform pin')
        child = read('charts/openg2p-registry/Chart.yaml')
        if child['name'] != dependency['name'] or child['version'] != pin['platformVersion']:
            raise ValueError('Incompatible packaged Registry dependency')
    return pin


def require_deployable(environment):
    """Only dev and staging deploy the OAN chart, and only with the pin made for that environment."""
    if environment not in ENVIRONMENTS:
        raise ValueError('Deployment blocked: the pinned OAN chart is for another environment')
    pin = profile(environment)
    if pin.get('environment') != environment:
        raise ValueError('Deployment blocked: the pinned OAN chart is for another environment')


def values_url(environment):
    """The reviewed environment values file of the pinned oan-helm commit, with its checksum."""
    pin = profile(environment)
    values = pin.get('values') or {}
    commit, digest, path = values.get('commit', ''), values.get('sha256', ''), values.get('path', '')
    base = 'https://raw.githubusercontent.com/Centre-for-Open-Societal-Systems/oan-helm/'
    if not (re.fullmatch(r'[0-9a-f]{40}', commit) and re.fullmatch(r'[0-9a-f]{64}', digest)
            and re.fullmatch(r'environments/[a-z]+/values/[a-z-]+\.yaml', path)):
        raise ValueError('Environment values are not pinned (commit and sha256 required)')
    return base + commit + '/' + path, digest


def defaults(path, pin=None):
    pin = profile() if pin is None else pin
    verify(path, pin)
    with tarfile.open(path, 'r:gz') as archive:
        prefix = pin['name'] + '/'
        child = yaml.safe_load(archive.extractfile(prefix + 'charts/openg2p-registry/values.yaml'))
        parent = yaml.safe_load(archive.extractfile(prefix + 'values.yaml'))
    from deployment import merge
    result = {'registry': child}
    merge(result, parent)
    return result


if __name__ == '__main__':
    try:
        if sys.argv[1] == 'url':
            pin = profile()
            print(pin['repository'] + pin['name'] + '-' + pin['version'] + '.tgz')
        elif sys.argv[1] == 'values-url':
            print('%s %s' % values_url(sys.argv[2]))
        elif sys.argv[1] == 'require-deployable':
            require_deployable(sys.argv[2])
            print('PASS: registry promotion evidence accepted')
        elif sys.argv[1] == 'verify':
            verify(sys.argv[2])
            print('PASS: approved OAN chart archive and packaged platform')
        else:
            raise ValueError('Unknown chart action')
    except (ValueError, OSError, KeyError, tarfile.TarError, yaml.YAMLError):
        sys.exit('FAIL: missing, corrupt or incompatible approved OAN chart')
