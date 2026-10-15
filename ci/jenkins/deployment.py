#!/usr/bin/env python3
"""Prepare and guard an existing dev release; never print private values."""
import copy
import json
import os
from pathlib import Path
import re
import sys

import yaml

RELEASE = "farmer-registry"
# Registry UI hostnames of the new-dev release. farmer-registry-development replaces
# registry.farmer-dev now that the gen2-dev *-development names point at this box;
# the original name stays accepted until the release itself has been renamed.
NEW_DEV_HOSTNAMES = {
    "registry.farmer-dev.oanstaging.com",
    "farmer-registry-development.oanstaging.com",
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


def index(docs):
    result = {}
    for d in docs:
        key = (d["kind"], d["metadata"]["name"])
        if key in result:
            raise ValueError(f"Duplicate resource: {key}")
        if d["metadata"].get("namespace", "farmer") != "farmer":
            raise ValueError(f"Resource outside farmer: {key}")
        result[key] = d
    return result


def pod(d):
    spec = d.get("spec", {})
    if d.get("kind") == "CronJob":
        spec = spec.get("jobTemplate", {}).get("spec", {})
    return spec.get("template", {}).get("spec", {})


def envs(d):
    return {c["name"]: {e["name"]: e for e in c.get("env", [])}
            for c in pod(d).get("containers", [])}


def image_root(registry, tag):
    if not re.fullmatch(r"\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com", registry):
        raise ValueError("Expected an ap-south-1 ECR registry")
    if not re.fullmatch(r"[0-9a-f]{12}", tag):
        raise ValueError("Expected a 12-character commit image tag")
    return registry + "/openg2p/farmer-registry"


def identity_overlay():
    return load(Path(__file__).resolve().parents[1] / "identity/registry-new-dev.values.yaml")


def identity_env(suffix):
    component = {"staff-portal-ui": "staffUi", "staff-portal-api": "staffApi",
                 "partner-api": "partnerApi", "celery-worker": "celeryWorker"}.get(suffix)
    return identity_overlay()["registry"].get(component, {}).get("envVars", {})


def merge(target, overlay):
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def prepare(values, before, registry, tag, migrate_identity=False):
    root = image_root(registry, tag)
    old = index(before)
    if ("Deployment", RELEASE + "-staff-portal-api") not in old:
        raise ValueError("Existing Registry deployment required")
    values = copy.deepcopy(values)
    if not isinstance(values, dict) or not values.get("global", {}).get("registryHostname"):
        raise ValueError("Existing environment values required; refusing default-host installation")
    if values["global"]["registryHostname"] not in NEW_DEV_HOSTNAMES:
        raise ValueError("This pipeline targets only the verified new-dev Registry hostname")
    config = values.setdefault("registry", {})
    for component, (_, _, image) in COMPONENTS.items():
        config.setdefault(component, {}).setdefault("image", {}).update(repository=root + "/" + image, tag=tag)
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
    if migrate_identity:
        merge(values, identity_overlay())
    return values


def validate(before, after, registry, tag, migrate_identity=False):
    root = image_root(registry, tag)
    old, new = index(before), index(after)
    for key, previous in old.items():
        # Hook/revision Jobs are short-lived. Persistent release resources must
        # all remain, including dashboard, PVCs, Services and ingress routes.
        if key[0] == "Job" or previous.get("metadata", {}).get("annotations", {}).get("helm.sh/hook"):
            continue
        if key not in new:
            raise ValueError(f"Upgrade would remove {key}; explicit ownership migration required")
        current = new[key]
        if key[0] in ("Deployment", "StatefulSet"):
            if previous["spec"].get("selector") != current["spec"].get("selector"):
                raise ValueError(f"Immutable selector changed: {key}")
            old_env, new_env = envs(previous), envs(current)
            for container, variables in old_env.items():
                for name, value in variables.items():
                    if new_env.get(container, {}).get(name) != value:
                        suffix = key[1].removeprefix(RELEASE + "-")
                        approved = identity_env(suffix) if migrate_identity else {}
                        if name not in approved or new_env.get(container, {}).get(name) != {"name": name, "value": approved[name]}:
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
        if key == ("Deployment", RELEASE + "-dashboard-api"):
            if [c["image"] for c in pod(previous)["containers"]] != [c["image"] for c in pod(current)["containers"]]:
                raise ValueError("Dashboard image must be retained by this Registry deployment")
    for _, (kind, suffix, component) in COMPONENTS.items():
        key = (kind, RELEASE + "-" + suffix)
        if key not in new or not pod(new[key]).get("containers"):
            raise ValueError(f"Missing required image workload: {key}")
        expected = root + "/" + component + ":" + tag
        if pod(new[key])["containers"][0]["image"] != expected:
            raise ValueError(f"Wrong commit image: {key}")
    if migrate_identity:
        for suffix in ("staff-portal-ui", "staff-portal-api", "partner-api", "celery-worker"):
            current = new[("Deployment", RELEASE + "-" + suffix)]
            environments = list(envs(current).values())
            if len(environments) != 1:
                raise ValueError("Identity migration requires one application container per workload")
            for name, value in identity_env(suffix).items():
                if environments[0].get(name) != {"name": name, "value": value}:
                    raise ValueError(f"Identity migration was not rendered: {suffix}/{name}")
    for key, d in new.items():
        if key[1].startswith(("commons-", "farmer-connector")):
            raise ValueError(f"Registry must not own shared/connector resource: {key}")
        if key[0] in ("ClusterRole", "ClusterRoleBinding", "Namespace"):
            raise ValueError(f"Registry must remain namespace-scoped: {key}")
        for container in pod(d).get("containers", []):
            for e in container.get("env", []):
                if e["name"] in ("LOAD_GEO_DATA", "LOAD_SAMPLE_DATA", "LOAD_IMAGES") and e.get("value") != "false":
                    raise ValueError(f"Demo/geography loader enabled: {key}/{e['name']}")


def release_status(status, require_deployed=False):
    if status.get("name") != RELEASE or status.get("namespace") != "farmer":
        raise ValueError("Expected farmer-registry in namespace farmer")
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


def unchanged_release(before, current):
    if (release_status(before), before["version"]) != (release_status(current), current["version"]):
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
        images[component] = {"image": image, "digest": digest}
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
    migrate_identity = os.environ.get("APPLY_COMMONS_IDENTITY", "false") == "true"
    if migrate_identity:
        # No environment drift allowed through a broad guard bypass. Evidence is
        # bound to the checked-in values and expires after one hour.
        import importlib.util
        spec = importlib.util.spec_from_file_location("identity", Path(__file__).resolve().parents[1] / "identity/check.py")
        identity = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity)
        identity.evidence(os.environ["IDENTITY_EVIDENCE_FILE"])
    if action in ("status", "complete", "upgrade-mode"):
        status = load(args[0])
        state = release_status(status, require_deployed=action == "complete")
        if action == "upgrade-mode":
            print("recovery" if state == "failed" else "normal")
            return
        print(f"Helm revision {status['version']}: {state}")
    elif action == "unchanged":
        unchanged_release(load(args[0]), load(args[1]))
    elif action == "diagnose":
        for message in upgrade_diagnostic(Path(args[0]).read_text(encoding="utf-8", errors="replace")):
            print("Helm diagnostic: " + message)
    elif action in ("provenance", "outcome"):
        commit = os.environ.get("SOURCE_COMMIT", "")
        images = registry_provenance(os.environ["ECR_REGISTRY"], os.environ["IMAGE_TAG"], commit)
        if action == "outcome":
            status = load(args[0])
            release_status(status, require_deployed=True)
            Path(args[1]).write_text(json.dumps({"component": RELEASE, "namespace": "farmer",
                                           "sourceCommit": commit, "images": images,
                                           "helmRevision": status["version"], "outcome": "deployed"}) + "\n", encoding="utf-8")
    elif action == "prepare":
        result = prepare(load(args[0]), documents(args[1]), os.environ["ECR_REGISTRY"], os.environ["IMAGE_TAG"], migrate_identity)
        Path(args[2]).write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
    elif action == "validate":
        validate(documents(args[0]), documents(args[1]), os.environ["ECR_REGISTRY"], os.environ["IMAGE_TAG"], migrate_identity)
    else:
        raise ValueError("Unknown deployment action")
    print(f"PASS: dev deployment {action}")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
    except (KeyError, IndexError, OSError, yaml.YAMLError):
        print("FAIL: malformed or missing deployment input; private values were not printed", file=sys.stderr)
        raise SystemExit(1)
