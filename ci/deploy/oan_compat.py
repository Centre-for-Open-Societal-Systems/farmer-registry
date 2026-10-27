"""Bounded render corrections for the pinned OAN chart; preservation validation remains independent.

Never copy a saved workload or command over the candidate. Suppress only the
listed packaged environment defaults explicitly nulled in prepared values.
"""
import copy
import os
import sys

import yaml

from deployment import RELEASE, envs, index, load, pod
from oan_chart import profile, verify

OMITTABLE = {
    'staffApi': ('staff-portal-api', {
        'COMMON_DB_HOSTNAME', 'KEYCLOAK_BASE_URL', 'REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES',
        'REGISTRY_STAFF_PORTAL_API_VALIDATE_ATTRIBUTE_VALUES',
        'REGISTRY_CORE_MASTER_DATA_DB_HOSTNAME', 'REGISTRY_STAFF_PORTAL_API_MASTER_DATA_DB_HOSTNAME'}),
    'partnerApi': ('partner-api', {
        'COMMON_DB_HOSTNAME', 'KEYCLOAK_BASE_URL', 'NOTIFICATION_ENABLED', 'NOTIFICATION_PROVIDER_URL',
        'REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES',
        'REGISTRY_PARTNER_API_MASTER_DATA_DB_HOSTNAME'}),
    'celeryWorker': ('celery-worker', {'COMMON_DB_HOSTNAME', 'REGISTRY_CELERY_WORKERS_MASTER_DATA_DB_HOSTNAME',
                                     'REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES'}),
    'celeryBeat': ('celery-beat-producer', {
        'COMMON_DB_HOSTNAME', 'NOTIFICATION_ENABLED', 'NOTIFICATION_PROVIDER_URL',
        'REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES',
        'REGISTRY_CELERY_BEAT_MASTER_DATA_DB_HOSTNAME'}),
}


def render(documents, values):
    result = copy.deepcopy(documents)
    resources = index(result)
    for resource in result:
        envs(resource)  # Reject duplicate environment names before any omission.
    for component, (suffix, names) in OMITTABLE.items():
        resource = resources.get(('Deployment', RELEASE + '-' + suffix))
        if resource is None:
            continue
        config = values.get('registry', {}).get(component, {})
        # Only a null in BOTH public maps is an explicit omission. A literal or
        # Secret ref in either map must survive, including future app settings.
        omitted = {name for name in names if all(name in config.get(field, {}) and
                   config[field][name] is None for field in ('envVars', 'envVarsFrom'))}
        for container in pod(resource).get('containers', []) + pod(resource).get('initContainers', []):
            if 'env' in container:
                container['env'] = [entry for entry in container['env'] if entry['name'] not in omitted]
    return result


def main():
    if (os.environ.get('DELIVERY_ENVIRONMENT'), os.environ.get('HELM_NAMESPACE'),
            os.environ.get('HELM_RELEASE')) != ('dev', 'farmer', RELEASE):
        raise ValueError('OAN compatibility renderer requires dev/farmer')
    pin = verify(os.environ['OAN_CHART_ARCHIVE'])
    if pin['version'] != profile()['version']:
        raise ValueError('Compatibility corrections require review for another chart')
    values = load(os.environ['OAN_VALUES_FILE'])
    docs = [doc for doc in yaml.safe_load_all(sys.stdin) if isinstance(doc, dict)]
    docs = render(docs, values)
    if os.environ.get('OAN_CHART_ONLY', 'false') == 'true':
        docs = [doc for doc in docs if doc.get('kind') != 'Job']
    sys.stdout.write(yaml.safe_dump_all(docs, sort_keys=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Helm includes stderr in its diagnostics; never print private YAML.
        sys.exit('FAIL: approved OAN compatibility render rejected input')
