"""Verify the approved archive without extracting or resolving dependencies."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile

import yaml


def profile():
    return json.loads(Path(__file__).with_name('oan-chart.json').read_text(encoding='utf-8'))


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
    pin = profile()
    if environment != 'dev' or pin.get('environment') != environment:
        raise ValueError('Deployment blocked: the pinned OAN chart is for another environment')


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
