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


def seed_environment(result, values):
    """Add dbSeed.envVars / dbSeed.envVarsFrom to the db-seed Job.

    The platform chart's Job template renders no free-form environment, so these values
    never reach the Job on their own. Only literals and Secret references are added; a
    name the Job already sets is never overridden.
    """
    config = values.get('registry', {}).get('dbSeed', {})
    additions = []
    for name, value in (config.get('envVars') or {}).items():
        if value is not None:
            additions.append({'name': name, 'value': str(value)})
    for name, value in (config.get('envVarsFrom') or {}).items():
        if value is not None:
            additions.append({'name': name, 'valueFrom': value})
    if not additions:
        return
    jobs = [d for d in result if d.get('kind') == 'Job' and d['metadata']['name'] == RELEASE + '-db-seed']
    if len(jobs) != 1:
        raise ValueError('db-seed Job required to carry dbSeed environment')
    containers = [c for c in pod(jobs[0]).get('containers', []) if c['name'] == 'db-seed']
    if len(containers) != 1:
        raise ValueError('db-seed container required')
    present = {e['name'] for e in containers[0].setdefault('env', [])}
    if any(a['name'] in present for a in additions):
        raise ValueError('dbSeed environment would override the Job environment')
    containers[0]['env'].extend(additions)


def render(documents, values, environment=None):
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
    if environment == 'staging':
        seed_environment(result, values)
    return result


# The corrections above were reviewed against this platform; another one needs a new review.
REVIEWED_PLATFORMS = {'1.2.2-rc.614'}
# Environments that render the OAN chart, each into namespace farmer.
ENVIRONMENTS = ('dev', 'staging')


def main():
    environment = os.environ.get('DELIVERY_ENVIRONMENT')
    if (environment not in ENVIRONMENTS or os.environ.get('HELM_NAMESPACE') != 'farmer'
            or os.environ.get('HELM_RELEASE') != RELEASE):
        raise ValueError('OAN compatibility renderer requires dev/farmer or staging/farmer')
    pin = verify(os.environ['OAN_CHART_ARCHIVE'])
    if pin.get('environment') != environment:
        raise ValueError('Compatibility renderer pin belongs to another environment')
    if pin['version'] != profile(environment)['version'] or pin['platformVersion'] not in REVIEWED_PLATFORMS:
        raise ValueError('Compatibility corrections require review for another chart')
    values = load(os.environ['OAN_VALUES_FILE'])
    docs = [doc for doc in yaml.safe_load_all(sys.stdin) if isinstance(doc, dict)]
    docs = render(docs, values, environment)
    if os.environ.get('OAN_CHART_ONLY', 'false') == 'true':
        docs = [doc for doc in docs if doc.get('kind') != 'Job']
    sys.stdout.write(yaml.safe_dump_all(docs, sort_keys=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Helm includes stderr in its diagnostics; never print private YAML.
        sys.exit('FAIL: approved OAN compatibility render rejected input')
