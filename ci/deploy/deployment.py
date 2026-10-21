#!/usr/bin/env python3
"""Prepare and guard an existing dev release; never print private values."""
import copy
import json
import os
from pathlib import Path
import re
import sys
import uuid

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from environments import configuration, namespace

RELEASE = "farmer-registry"
# Exact verified Registry UI hostnames of the new-dev release. Keep installed
# names valid during hostname migrations without rewriting the release's routes.
NEW_DEV_HOSTNAMES = {
    "registry.farmer-dev.oanstaging.com",
    "farmer-registry-development.oanstaging.com",
    "farmer-registry.development.oanstaging.com",
}
COMPONENTS = {
    "staffApi": ("Deployment", "staff-portal-api", "staff-api"),
    "staffUi": ("Deployment", "staff-portal-ui", "staff-ui"),
    "partnerApi": ("Deployment", "partner-api", "partner-api"),
    "celeryWorker": ("Deployment", "celery-worker", "celery"),
    "celeryBeat": ("Deployment", "celery-beat-producer", "celery"),
    "dbSeed": ("Job", "db-seed", "db-seed"),
    "sanity": ("Job", "sanity", "sanity-tests"),
}


def load(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def documents(path):
    return [d for d in yaml.safe_load_all(Path(path).read_text(encoding="utf-8")) if isinstance(d, dict)]


def schema_probe(api, image):
    """Read the DB with existing Secret references while API replicas are stopped."""
    if api.get('metadata', {}).get('name') != RELEASE + '-staff-portal-api' or api['metadata'].get('namespace') != 'far':
        raise ValueError('Schema probe requires the staging staff API Deployment')
    if not re.fullmatch(r'\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com/openg2p/farmer-registry/staff-api:[a-f0-9]{12}@sha256:[a-f0-9]{64}', image):
        raise ValueError('Schema probe requires the tested immutable staging API image')
    source = pod(api)
    containers = [c for c in source['containers'] if c['name'] == 'staff-portal-api']
    if len(containers) != 1 or containers[0].get('envFrom'):
        raise ValueError('Explicit staff API DB environment required')
    env = [copy.deepcopy(e) for e in containers[0].get('env', []) if e['name'].startswith('REGISTRY_STAFF_PORTAL_API_DB_')]
    names = [e['name'] for e in env]
    if len(set(names)) != len(names) or any('REGISTRY_STAFF_PORTAL_API_DB_' + key not in names for key in ('HOSTNAME', 'DBNAME', 'USERNAME', 'PASSWORD')):
        raise ValueError('Incomplete or duplicate schema probe DB configuration')
    database = next(e for e in env if e['name'].endswith('_DB_DBNAME'))
    if database.get('value') != configuration('staging')['registryDatabase']:
        raise ValueError('Schema probe cannot target another database')
    probe = {'restartPolicy': 'Never', 'automountServiceAccountToken': False,
             'containers': [{'name': 'schema', 'image': image, 'env': env,
                             'command': ['python3', '-c', (Path(__file__).resolve().parents[2] / 'scripts/operations/commons/check_geo_schema.py').read_text(encoding='utf-8')],
                             'resources': {'requests': {'cpu': '50m', 'memory': '64Mi'}, 'limits': {'memory': '256Mi'}}}]}
    for key in ('imagePullSecrets', 'serviceAccountName', 'securityContext', 'nodeSelector', 'tolerations'):
        if key in source:
            probe[key] = copy.deepcopy(source[key])
    if 'securityContext' in containers[0]:
        probe['containers'][0]['securityContext'] = copy.deepcopy(containers[0]['securityContext'])
    return {'apiVersion': 'batch/v1', 'kind': 'Job',
            'metadata': {'name': 'farmer-schema-' + uuid.uuid4().hex[:12], 'namespace': 'far'},
            'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': 90, 'ttlSecondsAfterFinished': 300,
                     'template': {'metadata': {'annotations': {'sidecar.istio.io/inject': 'false'}}, 'spec': probe}}}


def index(docs, environment="dev"):
    result = {}
    for d in docs:
        key = (d["kind"], d["metadata"]["name"])
        if key in result:
            raise ValueError(f"Duplicate resource: {key}")
        if d["metadata"].get("namespace", namespace(environment)) != namespace(environment):
            raise ValueError(f"Resource outside selected environment: {key}")
        result[key] = d
    return result


def pod(d):
    spec = d.get("spec", {})
    if d.get("kind") == "CronJob":
        spec = spec.get("jobTemplate", {}).get("spec", {})
    return spec.get("template", {}).get("spec", {})


def envs(d, include_init=True):
    result = {}
    for container in pod(d).get("containers", []) + (pod(d).get("initContainers", []) if include_init else []):
        entries = container.get("env", [])
        variables = {e["name"]: e for e in entries}
        if container["name"] in result or len(variables) != len(entries):
            raise ValueError("Duplicate workload container/environment entry")
        result[container["name"]] = variables
    return result


def reconcile_dev(values, before):
    """Carry installed literals and references through the chart's public values."""
    old = index(before)
    packaged = {}
    if os.environ.get('OAN_CHART_ARCHIVE'):
        from oan_chart import defaults
        packaged = defaults(os.environ['OAN_CHART_ARCHIVE'])
    for component, (kind, suffix, _) in COMPONENTS.items():
        if kind != 'Deployment':
            continue
        previous = old.get((kind, RELEASE + '-' + suffix))
        if previous is None:
            continue
        target = values['registry'].setdefault(component, {})
        installed = {}
        for variables in envs(previous).values():
            for name, entry in variables.items():
                if name in installed and installed[name] != entry:
                    raise ValueError('Installed init/application environments cannot share chart values')
                installed[name] = entry
        for field in ('envVars', 'envVarsFrom'):
            for name in packaged.get('registry', {}).get(component, {}).get(field, {}):
                if name not in installed:
                    target.setdefault(field, {})[name] = None
                    other = 'envVarsFrom' if field == 'envVars' else 'envVars'
                    target.setdefault(other, {})[name] = None
        for name, entry in installed.items():
            field, other = ('envVarsFrom', 'envVars') if 'valueFrom' in entry else ('envVars', 'envVarsFrom')
            value = entry.get('valueFrom', entry.get('value', ''))
            if '{{' in json.dumps(value):
                raise ValueError('Installed environment contains template syntax; explicit reconciliation required')
            target.setdefault(field, {})[name] = copy.deepcopy(value)
            # Null removes a packaged default from the other Helm map.
            target.setdefault(other, {})[name] = None
    dashboard = old.get(('Deployment', RELEASE + '-dashboard-api'))
    if dashboard:
        containers = pod(dashboard)['containers']
        if len(containers) != 1:
            raise ValueError('Dashboard container layout cannot be represented')
        image = containers[0]['image']
        repository, sep, digest = image.partition('@')
        target = values.setdefault('dashboardApi', {})
        target['enabled'] = True
        if sep:
            target['image'] = {'repository': repository, 'digest': digest}
        else:
            repository, sep, tag = image.rpartition(':')
            if not sep:
                raise ValueError('Installed dashboard requires an explicit image tag')
            target['image'] = {'repository': repository, 'tag': tag, 'digest': None}
        variables = envs(dashboard)[containers[0]['name']]
        for name, field in [('GEO_LEVEL_TOTALS', 'geoLevelTotals'), ('ALLOWED_ORIGINS', 'allowedOrigins')]:
            if name in variables:
                target[field] = json.loads(variables[name]['value'])
        for name, field in [('DB_POOL_MIN_SIZE', 'minSize'), ('DB_POOL_MAX_SIZE', 'maxSize')]:
            if name in variables:
                target.setdefault('dbPool', {})[field] = int(variables[name]['value'])
    return values


def image_root(registry, tag):
    if not re.fullmatch(r"\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com", registry):
        raise ValueError("Expected an ap-south-1 ECR registry")
    if not re.fullmatch(r"[0-9a-f]{12}", tag):
        raise ValueError("Expected a 12-character commit image tag")
    return registry + "/openg2p/farmer-registry"


def identity_overlay(environment="dev"):
    return load(Path(__file__).resolve().parents[2] / "helm/environments" / environment / "registry-identity.yaml")


def identity_env(suffix, environment="dev"):
    component = {"staff-portal-ui": "staffUi", "staff-portal-api": "staffApi",
                 "partner-api": "partnerApi", "celery-worker": "celeryWorker"}.get(suffix)
    values = identity_overlay(environment)["registry"].get(component, {})
    return {**values.get("envVarsFrom", {}), **values.get("envVars", {})}


def env_entry(name, value):
    """Render the chart's literal-or-valueFrom env contract for validation."""
    return {"name": name, "valueFrom" if isinstance(value, dict) else "value": value}


def master_data_env(suffix, environment="dev"):
    return {name: value for name, value in identity_env(suffix, environment).items()
            if name.endswith(("_MASTER_DATA_CLIENT_ID", "_MASTER_DATA_CLIENT_SECRET"))}


def location_overlay(environment="dev"):
    if environment != "dev":
        return {}
    return load(Path(__file__).resolve().parents[2] / "helm/environments/dev/registry-location.yaml")


def location_env(suffix, environment="dev"):
    component = {"staff-portal-ui": "staffUi", "staff-portal-api": "staffApi",
                 "partner-api": "partnerApi", "celery-worker": "celeryWorker"}.get(suffix)
    return location_overlay(environment).get("registry", {}).get(component, {}).get("envVars", {})


def merge(target, overlay):
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def prepare(values, before, registry, tag, migrate_identity=False, environment="dev", images=None):
    root = image_root(registry, tag)
    old = index(before, environment)
    if ("Deployment", RELEASE + "-staff-portal-api") not in old:
        raise ValueError("Existing Registry deployment required")
    values = copy.deepcopy(values)
    if not isinstance(values, dict) or not values.get("global", {}).get("registryHostname"):
        raise ValueError("Existing environment values required; refusing default-host installation")
    allowed = NEW_DEV_HOSTNAMES if environment == "dev" else {configuration(environment)["registryHostname"]}
    if values["global"]["registryHostname"] not in allowed:
        raise ValueError("This pipeline targets only the verified new-dev Registry hostname" if environment == "dev"
                         else "Registry hostname does not match staging")
    config = values.setdefault("registry", {})
    if environment == 'dev':
        reconcile_dev(values, before)
    # Some installed dev gateways are in the release manifest but absent from
    # saved values. Carry them into rc.544's owning values instead of falling
    # back to "internal"; validate still requires the whole route unchanged.
    if environment == "dev":
        for suffix, path in {
            "staff-portal-ui": ("staffUi",),
            "staff-portal-api": ("staffApi",),
            "partner-api": ("partnerApi",),
            "id-generator": ("idgenerator", "idGenerator"),
        }.items():
            route = old.get(("VirtualService", RELEASE + "-" + suffix))
            if route is None:
                continue
            gateways = route.get("spec", {}).get("gateways", [])
            if not isinstance(gateways, list) or len(gateways) != 1 or not isinstance(gateways[0], str) or not gateways[0].strip():
                raise ValueError(f"Installed gateway cannot be represented by the pinned chart: {suffix}")
            target = config
            for part in path:
                target = target.setdefault(part, {})
            target.setdefault("istio", {}).setdefault("virtualservice", {})["gateway"] = gateways[0]
    for component, (_, _, image) in COMPONENTS.items():
        pinned_tag = images[image]["tag"] + "@" + images[image]["digest"] if images else tag
        config.setdefault(component, {}).setdefault("image", {}).update(repository=root + "/" + image, tag=pinned_tag)
        if images:
            # Bitnami image helpers prefer digest to tag; overwrite saved pins.
            config[component]['image']['digest'] = ''
    if environment == 'dev' and images:
        values.setdefault('analytics', {})['image'] = {
            'repository': root + '/db-seed',
            'tag': images['db-seed']['tag'] + '@' + images['db-seed']['digest']}
    # rc.544's chart omits AWE worker variables previously added by COSS. Carry
    # their exact literals/Secret refs forward, without capturing Secret data.
    worker = old.get(("Deployment", RELEASE + "-celery-worker"), {})
    for container in envs(worker).values():
        for name, item in container.items():
            if name.startswith("REGISTRY_CELERY_WORKERS_AWE_"):
                target = "envVarsFrom" if "valueFrom" in item else "envVars"
                config["celeryWorker"].setdefault(target, {})[name] = item.get("valueFrom", item.get("value"))
    config["dbSeed"].update(loadGeoData=False, loadSampleData=False, loadImages=False, loadTemplates=True)
    config["dbSeed"].setdefault("intakeSeed", {})["enabled"] = False
    # Deployment smoke only; the e2e fixture suite creates users and synthetic
    # records. Do not run those mutations on dev as a side effect of merging.
    config["sanity"].update(enabled=True, runE2e=False, failOnError=True)
    values.setdefault("analytics", {}).setdefault("bulkSample", {})["enabled"] = False
    # rc.544 lacks the adopted layout's automatic reporting generator.
    # Maintained SQL reports and their refresh job remain enabled.
    values["analytics"].setdefault("reportingViews", {})["generate"] = False
    # Do not turn on new publishing/import jobs in shared Superset by default.
    values["analytics"].setdefault("dashboards", {}).setdefault("enabled", False)
    values.setdefault("mapsContent", {}).setdefault("enabled", False)
    # This narrow credential repair also applies on normal dev promotions.
    for component, (_, suffix, _) in COMPONENTS.items():
        approved = master_data_env(suffix, environment)
        for name, value in approved.items():
            target, other = ("envVarsFrom", "envVars") if isinstance(value, dict) else ("envVars", "envVarsFrom")
            config[component].setdefault(target, {})[name] = copy.deepcopy(value)
            config[component].get(other, {}).pop(name, None)
    if migrate_identity:
        merge(values, identity_overlay(environment))
    # Repair stale Master Data endpoints alongside the approved service binding.
    # Qualify the Commons service explicitly across namespace boundaries.
    merge(values, location_overlay(environment))
    if environment == "staging":
        # rc.544 stopped emitting legacy MDS DB settings and two UI toggles.
        # Carry their exact installed values/Secret refs through the owning
        # values, without hardcoding private configuration or relaxing validate.
        for component, (_, suffix, _) in COMPONENTS.items():
            previous = old.get(("Deployment", RELEASE + "-" + suffix), {})
            for variables in envs(previous).values():
                for name, item in variables.items():
                    if "_MASTER_DATA_DB_" not in name and not (
                        component == "staffUi" and name in ("PAGE_SIZE", "PARTNER_IMPORT_EXPORT_ENABLE")
                    ):
                        continue
                    target = "envVarsFrom" if "valueFrom" in item else "envVars"
                    config[component].setdefault(target, {})[name] = copy.deepcopy(item.get("valueFrom", item.get("value")))
        if not images:
            raise ValueError("Staging requires a tested image set pinned by digest")
        merge(values, identity_overlay("staging"))
    return values


def validate(before, after, registry, tag, migrate_identity=False, environment="dev", images=None):
    root = image_root(registry, tag)
    old, new = index(before, environment), index(after, environment)
    for key, previous in old.items():
        # Hook/revision Jobs are short-lived. Persistent release resources must
        # all remain, including dashboard, PVCs, Services and ingress routes.
        if key[0] == "Job" or previous.get("metadata", {}).get("annotations", {}).get("helm.sh/hook"):
            continue
        if key not in new:
            raise ValueError(f"Upgrade would remove {key}; explicit ownership migration required")
        current = new[key]
        if previous.get('metadata', {}).get('labels', {}).get('app.kubernetes.io/managed-by') != current.get('metadata', {}).get('labels', {}).get('app.kubernetes.io/managed-by'):
            raise ValueError(f'Existing Helm manager changed: {key}')
        for field in ('ownerReferences',):
            if previous.get('metadata', {}).get(field) != current.get('metadata', {}).get(field):
                raise ValueError(f'Existing ownership changed: {key}')
        for field in ('meta.helm.sh/release-name', 'meta.helm.sh/release-namespace'):
            if previous.get('metadata', {}).get('annotations', {}).get(field) != current.get('metadata', {}).get('annotations', {}).get(field):
                raise ValueError(f'Existing Helm ownership changed: {key}')
        if key[0] in ("Deployment", "StatefulSet"):
            if previous["spec"].get("selector") != current["spec"].get("selector"):
                raise ValueError(f"Immutable selector changed: {key}")
            old_env, new_env = envs(previous), envs(current)
            for group in ('containers', 'initContainers'):
                old_containers = {c['name']: c for c in pod(previous).get(group, [])}
                new_containers = {c['name']: c for c in pod(current).get(group, [])}
                if old_containers.keys() != new_containers.keys():
                    raise ValueError(f'Existing container layout changed: {key}/{group}')
                for name, container in old_containers.items():
                    if container.get('envFrom') != new_containers[name].get('envFrom'):
                        raise ValueError(f'Existing environment/Secret sources changed: {key}/{name}')
                    if group == 'initContainers' and container.get('image') != new_containers[name].get('image'):
                        raise ValueError(f'Existing init image changed: {key}/{name}')
            for container, variables in old_env.items():
                for name, value in variables.items():
                    if new_env.get(container, {}).get(name) != value:
                        suffix = key[1].removeprefix(RELEASE + "-")
                        approved = dict(identity_env(suffix, environment) if migrate_identity or environment == "staging" else master_data_env(suffix, environment))
                        approved.update(location_env(suffix, environment))
                        if name not in approved or new_env.get(container, {}).get(name) != env_entry(name, approved[name]):
                            raise ValueError(f"Existing environment/Secret reference changed: {key[1]}/{container}/{name}")
            if pod(previous).get("imagePullSecrets", []) != pod(current).get("imagePullSecrets", []):
                raise ValueError(f"Image-pull credentials changed: {key}")
        if key[0] == "VirtualService" and previous["spec"] != current["spec"]:
            raise ValueError(f"Existing ingress route changed: {key}")
        if key[0] == "Service":
            for field in ("type", "ports", "selector", "externalName"):
                if previous["spec"].get(field) != current["spec"].get(field):
                    raise ValueError(f"Existing service routing changed: {key}/{field}")
        if key[0] == "PersistentVolumeClaim" and previous["spec"] != current["spec"]:
            raise ValueError(f"Persistent volume claim changed: {key}")
        if key[0] == "Secret" and any(previous.get(field) != current.get(field) for field in ("data", "stringData", "type")):
            raise ValueError(f"Existing Secret contents changed: {key}")
        if key == ("Deployment", RELEASE + "-dashboard-api"):
            if [c["image"] for c in pod(previous)["containers"]] != [c["image"] for c in pod(current)["containers"]]:
                raise ValueError("Dashboard image must be retained by this Registry deployment")
        if environment == 'dev' and images:
            for group in ('containers', 'initContainers'):
                current_images = {c['name']: c.get('image') for c in pod(current).get(group, [])}
                for container in pod(previous).get(group, []):
                    previous_image = container.get('image', '')
                    built = any(previous_image.startswith(root + '/' + component + ':') or previous_image.startswith(root + '/' + component + '@') for component in images)
                    if not built and container.get('image') != current_images.get(container['name']):
                        raise ValueError(f'Optional component image changed: {key}/{container["name"]}')
    for _, (kind, suffix, component) in COMPONENTS.items():
        key = (kind, RELEASE + "-" + suffix)
        if key not in new or not pod(new[key]).get("containers"):
            raise ValueError(f"Missing required image workload: {key}")
        expected = root + "/" + component + ":" + (images[component]["tag"] + "@" + images[component]["digest"] if images else tag)
        if pod(new[key])["containers"][0]["image"] != expected:
            raise ValueError(f"Wrong commit image: {key}")
    public = new.get(("Deployment", RELEASE + "-staff-portal-ui-public"))
    if public:
        expected = root + "/staff-ui:" + (images["staff-ui"]["tag"] + "@" + images["staff-ui"]["digest"] if images else tag)
        if [c.get("image") for c in pod(public).get("containers", [])] != [expected]:
            raise ValueError("Public staff UI must use the accepted Registry staff UI image")
    if migrate_identity:
        for suffix in ("staff-portal-ui", "staff-portal-api", "partner-api", "celery-worker"):
            current = new[("Deployment", RELEASE + "-" + suffix)]
            environments = list(envs(current, include_init=False).values())
            if len(environments) != 1:
                raise ValueError("Identity migration requires one application container per workload")
            for name, value in identity_env(suffix).items():
                if environments[0].get(name) != env_entry(name, value):
                    raise ValueError(f"Identity migration was not rendered: {suffix}/{name}")
    if environment == "dev":
        for suffix in ("staff-portal-ui", "staff-portal-api", "partner-api", "celery-worker"):
            current = new.get(("Deployment", RELEASE + "-" + suffix), {})
            environments = list(envs(current, include_init=False).values())
            if len(environments) != 1:
                raise ValueError("Master Data routing requires one application container per workload")
            for name, value in location_env(suffix).items():
                if environments[0].get(name) != {"name": name, "value": value}:
                    raise ValueError(f"Master Data routing was not rendered: {suffix}/{name}")
            for name, value in master_data_env(suffix).items():
                if environments[0].get(name) != env_entry(name, value):
                    raise ValueError(f"Master Data credentials were not rendered: {suffix}/{name}")
    if environment == "staging":
        if not images:
            raise ValueError("Staging requires immutable image digests")
        partner = next(iter(envs(new[("Deployment", RELEASE + "-partner-api")]).values()))
        if partner.get("REGISTRY_PARTNER_API_SIGNATURE_VALIDATION_ENABLED") != {"name": "REGISTRY_PARTNER_API_SIGNATURE_VALIDATION_ENABLED", "value": "true"}:
            raise ValueError("Partner signature verification must stay enabled")
        for suffix in ("staff-portal-api", "partner-api", "celery-worker"):
            current = next(iter(envs(new[("Deployment", RELEASE + "-" + suffix)]).values()))
            for name, value in identity_env(suffix, "staging").items():
                if current.get(name) != env_entry(name, value):
                    raise ValueError(f"Staging staff identity was not rendered: {suffix}/{name}")
    for key, d in new.items():
        if environment == 'dev' and key not in old and key[0] != 'Job':
            raise ValueError(f'Unexpected persistent resource: {key}')
        if key[1].startswith(("commons-", "farmer-connector")):
            raise ValueError(f"Registry must not own shared/connector resource: {key}")
        if key[0] in ("ClusterRole", "ClusterRoleBinding", "Namespace", "PersistentVolume",
                      "CustomResourceDefinition", "StorageClass", "APIService",
                      "MutatingWebhookConfiguration", "ValidatingWebhookConfiguration"):
            raise ValueError(f"Registry must remain namespace-scoped: {key}")
        for container in pod(d).get("containers", []):
            if environment == 'dev' and images:
                for component in images:
                    prefix = root + '/' + component
                    image = container.get('image', '')
                    if image.startswith((prefix + ':', prefix + '@')) and image != prefix + ':' + images[component]['tag'] + '@' + images[component]['digest']:
                        raise ValueError(f'Built component did not use recorded digest: {key}')
            for e in container.get("env", []):
                if e["name"] in ("LOAD_GEO_DATA", "LOAD_SAMPLE_DATA", "LOAD_IMAGES") and e.get("value") != "false":
                    raise ValueError(f"Demo/geography loader enabled: {key}/{e['name']}")


def release_status(status, require_deployed=False, environment="dev"):
    if status.get("name") != RELEASE or status.get("namespace") != namespace(environment):
        raise ValueError("Expected farmer-registry in the selected environment namespace")
    revision = status.get("version")
    if type(revision) is not int or revision < 1:
        raise ValueError("Expected a positive Helm release revision")
    state = status.get("info", {}).get("status")
    allowed = ("deployed",) if require_deployed else ("deployed", "failed")
    if state not in allowed:
        # Do not print arbitrary Helm descriptions, which may contain private data.
        known = state if state in ("pending-install", "pending-upgrade", "pending-rollback",
                                  "uninstalling", "uninstalled", "superseded", "failed") else "unknown"
        raise ValueError(f"Helm revision {revision} is {known}; resolve Helm state first")
    return state


def unchanged_release(before, current, environment="dev"):
    if (release_status(before, environment=environment), before["version"]) != (release_status(current, environment=environment), current["version"]):
        raise ValueError("Helm revision/state changed during preflight; rerun against the latest release")


def registry_provenance(registry, tag, commit):
    root = image_root(registry, tag)
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not commit.startswith(tag):
        raise ValueError("Invalid Registry source provenance")
    images = {}
    for line in Path("service-outcomes/registry-images.tsv").read_text(encoding="utf-8").splitlines():
        component, image, digest = line.split("\t")
        if component not in {c[2] for c in COMPONENTS.values()} or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("Invalid Registry image provenance")
        if image != root + "/" + component + ":" + tag or component in images:
            raise ValueError("Invalid Registry image provenance")
        images[component] = {"image": image, "tag": tag, "digest": digest}
    if set(images) != {c[2] for c in COMPONENTS.values()}:
        raise ValueError("Missing Registry image provenance")
    return images


def upgrade_diagnostic(log):
    """Classify Helm errors without echoing arbitrary manifests or secret values."""
    patterns = [
        (r'BackoffLimitExceeded|backoff limit', 'A hook Job exhausted its retries.'),
        (r'ImagePullBackOff|ErrImagePull|pull access denied', 'A workload could not pull its image.'),
        (r'timed out|context deadline exceeded', 'Helm timed out waiting for resources or hooks.'),
        (r'another operation .*in progress', 'Another Helm operation is in progress.'),
        (r'forbidden|Unauthorized', 'Kubernetes authorization rejected the operation.'),
        (r'cannot patch|field is immutable', 'Kubernetes rejected a resource update.'),
        (r'failed (?:pre|post)-(?:install|upgrade)|hooks? failed', 'A Helm lifecycle hook failed.'),
        (r'no matches for kind|resource mapping not found', 'A required Kubernetes API or CRD is unavailable.'),
        (r'connection refused|no such host|TLS handshake timeout', 'The Kubernetes endpoint could not be reached.'),
    ]
    matches = [message for pattern, message in patterns if re.search(pattern, log, re.I)]
    return matches or ['Helm failed with an unclassified error; raw output was withheld because it may contain secrets.']


def main():
    action, *args = sys.argv[1:]
    environment = os.environ.get("DELIVERY_ENVIRONMENT", "dev")
    namespace(environment)
    images = None
    if environment == "staging":
        from staging import evidence
        record = evidence(os.environ["STAGING_EVIDENCE_FILE"], os.environ["SOURCE_COMMIT"])
        images = record["registry"]["images"]
        os.environ["ECR_REGISTRY"] = record["registry"]["registry"]
        os.environ["IMAGE_TAG"] = record["registry"]["sourceCommit"][:12]
    elif action in ('prepare', 'validate', 'provenance', 'outcome', 'attempt'):
        images = registry_provenance(os.environ['ECR_REGISTRY'], os.environ['IMAGE_TAG'], os.environ.get('SOURCE_COMMIT', ''))
    migrate_identity = os.environ.get("APPLY_COMMONS_IDENTITY", "false") == "true"
    if environment == "staging" and migrate_identity:
        raise ValueError("Dev Commons identity migration cannot be used for staging")
    if migrate_identity:
        # No environment drift allowed through a broad guard bypass. Evidence is
        # bound to the checked-in values and expires after one hour.
        import importlib.util
        spec = importlib.util.spec_from_file_location("identity", Path(__file__).resolve().parents[2] / "scripts/operations/identity/check.py")
        identity = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity)
        identity.evidence(os.environ["IDENTITY_EVIDENCE_FILE"])
    if action == 'schema-probe':
        if environment != 'staging':
            raise ValueError('Stopped-workload probe is staging-only')
        api_image = images['staff-api']
        image = api_image['repository'] + ':' + api_image['tag'] + '@' + api_image['digest']
        Path(args[1]).write_text(json.dumps(schema_probe(load(args[0]), image)), encoding='utf-8')
    elif action in ("status", "complete", "upgrade-mode"):
        status = load(args[0])
        state = release_status(status, require_deployed=action == "complete", environment=environment)
        if action == "upgrade-mode":
            print("recovery" if state == "failed" else "normal")
            return
        print(f"Helm revision {status['version']}: {state}")
    elif action == "unchanged":
        unchanged_release(load(args[0]), load(args[1]), environment)
    elif action == "diagnose":
        for message in upgrade_diagnostic(Path(args[0]).read_text(encoding="utf-8", errors="replace")):
            print("Helm diagnostic: " + message)
    elif action in ("provenance", "outcome", "attempt"):
        commit = os.environ.get("SOURCE_COMMIT", "")
        if environment == "dev":
            images = registry_provenance(os.environ["ECR_REGISTRY"], os.environ["IMAGE_TAG"], commit)
        if action == 'attempt':
            if environment != 'dev':
                raise ValueError('OAN attempt record is dev only')
            from oan_chart import profile
            Path(args[0]).write_text(json.dumps({'component': RELEASE, 'namespace': 'farmer',
                'sourceCommit': commit, 'images': images, 'chart': profile(),
                'helmRevision': None, 'outcome': 'not-completed',
                'verification': 'deployment-did-not-complete-all-gates'}) + '\n', encoding='utf-8')
        if action == "outcome":
            if environment == 'dev':
                from oan_chart import profile
            status = load(args[0])
            release_status(status, require_deployed=True, environment=environment)
            Path(args[1]).write_text(json.dumps({"component": RELEASE, "namespace": namespace(environment),
                                           "sourceCommit": commit, "images": images,
                                           "helmRevision": status["version"], "outcome": "deployed",
                                           **({"chart": profile(), "verification": "preservation-rollout-schema-passed"} if environment == 'dev' else {})}) + "\n", encoding="utf-8")
    elif action == "prepare":
        result = prepare(load(args[0]), documents(args[1]), os.environ["ECR_REGISTRY"], os.environ["IMAGE_TAG"], migrate_identity, environment, images)
        Path(args[2]).write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
    elif action == "validate":
        validate(documents(args[0]), documents(args[1]), os.environ["ECR_REGISTRY"], os.environ["IMAGE_TAG"], migrate_identity, environment, images)
        if environment == "staging":
            from staging import manifest_hash
            if manifest_hash(documents(args[1])) != record["candidateManifestHash"]:
                raise ValueError("Candidate resources differ from the rehearsed manifests")
    else:
        raise ValueError("Unknown deployment action")
    print(f"PASS: {environment} deployment {action}")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
    except (KeyError, IndexError, OSError, yaml.YAMLError):
        print("FAIL: malformed or missing deployment input; private values were not printed", file=sys.stderr)
        raise SystemExit(1)
