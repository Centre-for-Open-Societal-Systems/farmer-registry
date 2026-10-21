"""Chart-only cutover: no application/configuration changes or Job execution."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import sys

import yaml

from deployment import documents, envs, index, load, pod, reconcile_dev, release_status
from oan_chart import profile


def metadata_only(doc):
    doc = copy.deepcopy(doc)
    def visit(value):
        if isinstance(value, dict):
            # The only reviewed metadata difference in this chart switch.
            value.get('metadata', {}).get('labels', {}).pop('helm.sh/chart', None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(doc)
    spec = pod(doc)
    for container in spec.get('containers', []) + spec.get('initContainers', []):
        container['env'] = sorted(container.get('env', []), key=lambda entry: entry['name'])
    return doc


def validate(before, after):
    old, new = index(before), index(after)
    if any(key[0] == 'Job' for key in new):
        raise ValueError('Cutover must suppress every Job')
    old = {k: v for k, v in old.items() if k[0] != 'Job'}
    if old.keys() != new.keys():
        raise ValueError('Cutover persistent resource inventory changed')
    for key in old:
        envs(old[key]); envs(new[key])  # Reject duplicate named environments.
        if metadata_only(old[key]) != metadata_only(new[key]):
            raise ValueError(f'Cutover changes installed configuration: {key}')


def backup_gate(directory, status, values, manifest, jobs):
    root = Path(directory)
    evidence = load(root / 'cutover-evidence.json')
    now = datetime.now(timezone.utc)
    verified = datetime.fromisoformat(evidence['verifiedAt'])
    if verified > now or now - verified > timedelta(hours=1):
        raise ValueError('Fresh cutover backup evidence required')
    release_status(status, require_deployed=True)
    commit = evidence['applicationCommit']
    if not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Recorded installed application commit required')
    from deployment import COMPONENTS
    installed = index(manifest)
    for kind, suffix, _ in COMPONENTS.values():
        if kind == 'Deployment':
            image = pod(installed[(kind, 'farmer-registry-' + suffix)])['containers'][0]['image']
            if not re.search(':' + commit[:12] + r'(?:@sha256:[0-9a-f]{64})?$', image):
                raise ValueError('Installed images differ from recorded application commit')
    if evidence['helmRevision'] != status['version'] or evidence['namespace'] != 'farmer' or evidence['release'] != 'farmer-registry':
        raise ValueError('Backup evidence does not cover this release revision')
    required = {'release.json', 'values.json', 'manifest.yaml', 'hooks.yaml', 'registry.dump', 'connector.dump'}
    if set(evidence['sha256']) != required or evidence['restoreVerified'] is not True:
        raise ValueError('Complete restore-verified private backup required')
    for name, checksum in evidence['sha256'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != checksum:
            raise ValueError('Private backup checksum failed')
    if any((root / name).stat().st_size == 0 for name in ('registry.dump', 'connector.dump')):
        raise ValueError('Database backup is empty')
    if load(root / 'release.json') != status or load(root / 'values.json') != values or documents(root / 'manifest.yaml') != manifest:
        raise ValueError('Release differs from the protected backup')
    reviewed = set(evidence['reviewedJobRemovals'])
    expected = {d['metadata']['name'] for d in manifest if d['kind'] == 'Job'}
    if reviewed != expected:
        raise ValueError('Review the exact completed Job records being removed')
    for job in jobs['items']:
        meta = job['metadata']
        if meta.get('labels', {}).get('app.kubernetes.io/instance') != 'farmer-registry' and not meta['name'].startswith('farmer-registry-') and meta['name'] not in reviewed:
            continue
        state = job.get('status', {})
        if state.get('active', 0) or not any(c.get('type') in ('Complete', 'Failed') and c.get('status') == 'True' for c in state.get('conditions', [])):
            raise ValueError('An affected Job is active or unfinished')


def main():
    action, *args = sys.argv[1:]
    if os.environ.get('DELIVERY_ENVIRONMENT') != 'dev' or os.environ.get('HELM_NAMESPACE') != 'farmer' or os.environ.get('HELM_RELEASE') != 'farmer-registry':
        raise ValueError('Chart cutover is dev/farmer only')
    if action == 'filter':
        docs = [d for d in yaml.safe_load_all(sys.stdin) if isinstance(d, dict) and d.get('kind') != 'Job']
        sys.stdout.write(yaml.safe_dump_all(docs, sort_keys=False))
    elif action == 'prepare':
        os.environ['OAN_CHART_ARCHIVE'] = args[3]
        values, before = load(args[0]), documents(args[1])
        if values.get('global', {}).get('registryHostname') not in __import__('deployment').NEW_DEV_HOSTNAMES:
            raise ValueError('Installed dev hostname required')
        reconcile_dev(values, before)
        # Preserve every installed application image, including both Celery pods.
        from deployment import COMPONENTS
        old = index(before)
        for component, (kind, suffix, _) in COMPONENTS.items():
            if kind == 'Job':
                continue
            image = pod(old[(kind, 'farmer-registry-' + suffix)])['containers'][0]['image']
            repository, sep, digest = image.partition('@')
            repository, colon, tag = repository.rpartition(':')
            if not colon:
                raise ValueError('Installed image needs an explicit tag for the chart-only cutover')
            values['registry'][component]['image'] = {'repository': repository, 'tag': tag + ('@' + digest if sep else ''), 'digest': ''}
        Path(args[2]).write_text(yaml.safe_dump(values, sort_keys=False), encoding='utf-8')
    elif action == 'validate':
        validate(documents(args[0]), documents(args[1]))
    elif action == 'backup':
        backup_gate(args[0], load(args[1]), load(args[2]), documents(args[3]), load(args[4]))
    elif action in ('installed', 'adopted'):
        releases = load(args[0])
        expected = profile()['name'] + '-' + profile()['version']
        allowed = ('deployed', 'failed') if action == 'adopted' else ('deployed',)
        if len(releases) != 1 or releases[0]['name'] != 'farmer-registry' or releases[0]['namespace'] != 'farmer' or releases[0]['chart'] != expected or releases[0]['status'] not in allowed:
            raise ValueError('Expected the approved OAN chart in the live release')
    elif action in ('outcome', 'attempt'):
        status = load(args[0])
        release_status(status, require_deployed=True)
        images = {d['metadata']['name']: {c['name']: c['image'] for c in pod(d).get('containers', [])}
                  for d in documents(args[1]) if pod(d).get('containers')}
        Path(args[2]).write_text(json.dumps({'component': 'farmer-registry', 'namespace': 'farmer',
            'mode': 'chart-only', 'chart': profile(), 'helmRevision': status['version'], 'images': images,
            'sourceCommit': load('/backup/cutover-evidence.json')['applicationCommit'],
            'verification': 'metadata-only-preservation-and-helm-readiness-passed' if action == 'outcome' else 'cutover-not-completed',
            'acceptance': 'pending-operational-checks'}) + '\n', encoding='utf-8')
    else:
        raise ValueError('Unknown cutover action')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, TypeError, KeyError, IndexError, OSError, yaml.YAMLError):
        # Exceptions may contain private YAML, paths or environment contents.
        sys.exit('FAIL: chart-only cutover gate rejected input; inspect private state')
