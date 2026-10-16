#!/usr/bin/env python3
"""Build optional services independently, promote digests, preserve release ownership.

Private subprocess output and release values never enter the outcome artifact.
Exit 2 means optional failures (Jenkins UNSTABLE); configuration errors exit 1.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
from environments import connector_settings, validate_cluster
sys.path.insert(0, str(ROOT / "scripts/operations/connector"))
MANIFEST = ROOT / "helm/openg2p-farmer-registry/values.yaml"
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
NAME = re.compile(r"[a-z][a-z0-9-]{0,62}")


class ServiceError(Exception):
    """Deliberately contains only a fixed safe error category."""

    def __init__(self, reason, provenance=None):
        super().__init__(reason)
        self.provenance = provenance or {}


class SkipService(Exception):
    pass


def command(args, cwd=None, input=None):
    # No shell expansion; Git/Helm output may contain credentials or private values.
    try:
        result = subprocess.run(args, cwd=cwd, input=input, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=1800)
    except (OSError, subprocess.TimeoutExpired):
        raise ServiceError("tool-unavailable-or-timeout") from None
    if result.returncode:
        if re.search(r"AccessDenied|Unauthorized|forbidden|authentication failed|permission denied", result.stderr, re.I):
            raise ServiceError("tool-authentication-or-authorization-failed")
        if "RepositoryNotFoundException" in result.stderr:
            raise ServiceError("image-repository-missing")
        raise ServiceError("command-failed-" + Path(args[0]).name)
    return result.stdout


def relative_file(root, path):
    if not isinstance(path, str) or not path:
        raise ServiceError("missing-application-layout")
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ServiceError("path-outside-source")
    return candidate


def image_specs(component):
    return component.get("images") or {"main": {"dockerfile": component["dockerfile"],
                                               "context": component.get("context", "."),
                                               "imageValues": [component["imageValues"]]}}


def configuration(path=MANIFEST, environment="dev"):
    if environment not in ("dev", "staging"):
        raise ValueError("Unknown environment")
    items = yaml.safe_load(path.read_text(encoding="utf-8"))["cossAddons"]["components"]
    seen = set()
    for item in items:
        for field in ("name", "release", "namespace"):
            if not NAME.fullmatch(item[field]):
                raise ValueError("Invalid component/release/namespace")
        if item["namespace"] != "farmer":
            raise ValueError("Farmer coordination must stay in the farmer namespace")
        if item["name"] in seen:
            raise ValueError("Duplicate component")
        seen.add(item["name"])
        if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git", item["repository"]):
            raise ValueError("Expected a credential-free GitHub repository URL")
        embedded = item.get("kind") == "registry-dashboard-api"
        if embedded and any(item.get(key) != value for key, value in {
            "name": "farmer-registry-dashboard-api", "release": "farmer-registry",
            "repository": "https://github.com/Centre-for-Open-Societal-Systems/farmer-registry-dashboard-api.git",
            "chart": "helm/openg2p-farmer-registry", "imageValues": "dashboardApi.image",
            "imageRepository": "openg2p/farmer-registry/dashboard-api",
        }.items()):
            raise ValueError("Dashboard API must retain its Farmer chart ownership")
        if item["release"] in ("commons", "commons-services", "farmer-connector") or (item["release"] == "farmer-registry" and not embedded):
            raise ValueError("Optional service must not adopt an existing shared/Registry/old connector release")
        if item.get("imageRepository") and not re.fullmatch(r"openg2p/[a-z0-9/-]+", item["imageRepository"]):
            raise ValueError("Invalid image repository")
    if environment == "staging":
        items = copy.deepcopy(items)
        for item in items:
            item["namespace"] = "far"
    return items


def configuration_hash():
    # Chart values are the sole service catalogue; unrelated chart settings do
    # not invalidate an otherwise identical service promotion record.
    addons = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["cossAddons"]
    return hashlib.sha256(json.dumps(addons, sort_keys=True).encode()).hexdigest()


def branch(environment, component):
    if environment not in ("dev", "staging"):
        raise ValueError("Unknown environment")
    return component.get("sourceBranch") or {"dev": "develop", "staging": "staging"}[environment]


def checkout(component, environment, destination, run=command, commit=None):
    repo = component["repository"]
    if commit is None:
        wanted = branch(environment, component)
        # ls-remote --exit-code returns 2 ONLY for no matching reference.
        # Network/auth errors must not be reported as missing code.
        try:
            result = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", repo,
                                     "refs/heads/" + wanted], capture_output=True, text=True, timeout=90)
        except (OSError, subprocess.TimeoutExpired):
            raise ServiceError("source-unavailable") from None
        if result.returncode == 2:
            raise SkipService("missing-branch")
        if result.returncode:
            raise ServiceError("source-authentication-or-network")
        lines = result.stdout.splitlines()
        if len(lines) != 1 or not SHA.fullmatch(lines[0].split()[0]):
            raise ServiceError("invalid-source-revision")
        commit = lines[0].split()[0]
    if not SHA.fullmatch(commit):
        raise ServiceError("invalid-source-revision")
    destination.mkdir(parents=True)
    run(["git", "init", "--quiet", str(destination)])
    run(["git", "-C", str(destination), "remote", "add", "origin", repo])
    run(["git", "-C", str(destination), "fetch", "--quiet", "--depth", "1", "origin", commit])
    run(["git", "-C", str(destination), "checkout", "--quiet", "--detach", "FETCH_HEAD"])
    if run(["git", "-C", str(destination), "rev-parse", "HEAD"]).strip() != commit:
        raise ServiceError("source-revision-changed")
    return commit


def layout(component, source):
    dockerfile = relative_file(source, component["dockerfile"])
    chart_root = ROOT if component.get("kind") == "registry-dashboard-api" else source
    chart = relative_file(chart_root, component["chart"])
    if not dockerfile.is_file() or not (chart / "Chart.yaml").is_file():
        raise SkipService("missing-application-files")
    if not component.get("imageValues"):
        raise SkipService("unverified-upstream-image-values")
    for spec in image_specs(component).values():
        if not relative_file(source, spec["dockerfile"]).is_file() or not relative_file(source, spec["context"]).is_dir():
            raise SkipService("missing-application-files")
    chart_metadata = yaml.safe_load((chart / "Chart.yaml").read_text(encoding="utf-8"))
    if chart_metadata.get("dependencies") and not (chart / "Chart.lock").is_file():
        raise ServiceError("chart-dependencies-not-locked")
    if component.get("kind") == "connector":
        module_spec = importlib.util.spec_from_file_location("connector_chart_signing", ROOT / "scripts/operations/connector/chart_signing.py")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        module.apply(chart)
    return dockerfile, chart


def chart_hash(chart):
    """Bind promotion/rehearsal to chart contents, excluding downloaded deps."""
    digest = hashlib.sha256()
    for file in sorted(chart.rglob("*")):
        if file.is_file() and not {"charts", "__pycache__", ".pytest_cache", ".git"}.intersection(file.relative_to(chart).parts):
            digest.update(file.relative_to(chart).as_posix().encode())
            digest.update(file.read_bytes())
    return digest.hexdigest()


def build_image(component, role, spec, commit, source, registry, run, tag=None):
    suffix = "-" + role if component.get("images") else ""
    repository_name = component.get("imageRepository", "openg2p/" + component["name"] + suffix)
    repository = registry + "/" + repository_name
    tag = tag or commit[:12]
    image = repository + ":" + tag
    upstream_image = image + "-upstream" if spec.get("overlay") else image
    run(["docker", "build", "--label", "org.opencontainers.image.source=" + component["repository"],
         "--label", "org.opencontainers.image.revision=" + commit,
         "-f", str(relative_file(source, spec["dockerfile"])), "-t", upstream_image, str(relative_file(source, spec["context"]))])
    rehearsal_result = None
    if spec.get("overlay"):
        overlay = relative_file(ROOT, spec["overlay"])
        run(["docker", "build", "--build-arg", "UPSTREAM_IMAGE=" + upstream_image,
             "--label", "org.opencontainers.image.source=" + component["repository"],
             "--label", "org.opencontainers.image.revision=" + commit,
             "--label", "org.openg2p.overlay.sha256=" + chart_hash(overlay),
             "-t", image, str(overlay)])
        runtime_test = ROOT / "tests/runtime/test_connector_media.py"
        rehearsal = ROOT / "scripts/operations/connector/rehearse.py"
        if runtime_test.is_file():
            run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "python",
                 "-v", str(runtime_test) + ":/tests/test_media.py:ro", image, "/tests/test_media.py"])
        if rehearsal.is_file():
            rehearsal_result = json.loads(run([sys.executable, str(rehearsal), image]).strip().splitlines()[-1])
            if not all(rehearsal_result.get(name) is True for name in ("schemaRerun", "failedDdlRolledBack", "failureRecovery", "duplicateSentOnce", "failedBoundaryRetried", "rollbackReconciled", "pollTimestampPersisted", "isolatedDatabases")):
                raise ServiceError("connector-schema-rehearsal-failed")
    pushed = run(["docker", "push", image])
    matches = re.findall(r"digest: (sha256:[0-9a-f]{64})\b", pushed)
    if len(set(matches)) != 1:
        raise ServiceError("missing-pushed-digest")
    digest = matches[0]
    published = run(["aws", "ecr", "describe-images", "--region", "ap-south-1",
                  "--repository-name", repository_name,
                  "--image-ids", "imageDigest=" + digest, "--query", "imageDetails[0].imageDigest",
                  "--output", "text"]).strip()
    if published != digest:
        raise ServiceError("missing-published-digest")
    result = {"repository": repository, "tag": tag, "digest": digest}
    if rehearsal_result:
        result["rehearsal"] = rehearsal_result
    return result


def build(component, environment, source, registry, run=command):
    commit = checkout(component, environment, source, run)
    built = {}
    try:
        _, chart = layout(component, source)
        overlays = {role: chart_hash(relative_file(ROOT, spec["overlay"]))
                    for role, spec in image_specs(component).items() if spec.get("overlay")}
        tag = commit[:12]
        if overlays:
            tag += "-" + hashlib.sha256(json.dumps(overlays, sort_keys=True).encode()).hexdigest()[:12]
        for role, spec in image_specs(component).items():
            built[role] = build_image(component, role, spec, commit, source, registry, run, tag)
    except (SkipService, ServiceError) as error:
        error.provenance = {"commit": commit}
        if built:
            error.provenance["images"] = built
        raise
    primary = next(iter(built.values()))
    result = dict(primary, commit=commit, chartHash=chart_hash(chart))
    if component.get("images"):
        result["images"] = built
    if overlays:
        result["overlayHashes"] = overlays
    return result


def docs(text):
    return [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]


def pod(doc):
    spec = doc.get("spec", {})
    if doc.get("kind") == "CronJob":
        spec = spec.get("jobTemplate", {}).get("spec", {})
    return spec.get("template", {}).get("spec", {})


def guard(before, after, namespace, image, release=None):
    """An optional update may change its image, never discard existing resources."""
    expected_images = {image} if isinstance(image, str) else set(image)
    def index(items):
        result = {}
        for d in items:
            key = d["kind"], d["metadata"]["name"]
            if key in result:
                raise ServiceError("duplicate-resource")
            if d["metadata"].get("namespace", namespace) != namespace:
                raise ServiceError("cross-namespace-resource")
            if release and key[1] != release and not key[1].startswith(release + "-"):
                raise ServiceError("shared-resource-name")
            if d["kind"] in ("Namespace", "ClusterRole", "ClusterRoleBinding", "PersistentVolume", "CustomResourceDefinition"):
                raise ServiceError("shared-resource")
            result[key] = d
        return result
    old, new = index(before), index(after)
    for key, previous in old.items():
        if key[0] == "Job" or previous.get("metadata", {}).get("annotations", {}).get("helm.sh/hook"):
            continue
        if key not in new:
            raise ServiceError("resource-removal")
        current = new[key]
        # Only workload images and checksum annotations may change on an upgrade.
        if key[0] in ("Deployment", "StatefulSet", "DaemonSet", "CronJob"):
            a, b = copy.deepcopy(previous["spec"]), copy.deepcopy(current["spec"])
            for spec in (a, b):
                template = spec.get("jobTemplate", {}).get("spec", spec).get("template", {})
                annotations = template.get("metadata", {}).get("annotations", {})
                for name in list(annotations):
                    if name.startswith("checksum/"):
                        del annotations[name]
                for container in template.get("spec", {}).get("containers", []):
                    container.pop("image", None)
            if a != b:
                raise ServiceError("workload-config-or-storage-changed")
        elif previous.get("spec", previous.get("data")) != current.get("spec", current.get("data")):
            raise ServiceError("routing-storage-or-config-changed")
    images = [c["image"] for d in new.values() for c in pod(d).get("containers", [])
              if d["kind"] != "Job"]
    if not expected_images.issubset(images):
        raise ServiceError("digest-image-not-rendered")
    for key in old.keys() & new.keys():
        previous = {c["name"]: c.get("image") for c in pod(old[key]).get("containers", [])}
        for c in pod(new[key]).get("containers", []):
            if c.get("image") != previous.get(c["name"]) and c.get("image") not in expected_images:
                raise ServiceError("unexpected-image-change")


def paused_connector(manifest):
    """No automatic process may run until upstream workers are identified."""
    for d in manifest:
        kind = d["kind"]
        if kind == "CronJob" and d["spec"].get("suspend") is not True:
            raise ServiceError("connector-scheduler-active")
        if kind in ("Deployment", "StatefulSet") and d["spec"].get("replicas", 1) != 0:
            raise ServiceError("connector-process-active")
        if kind in ("Job", "DaemonSet"):
            raise ServiceError("connector-job-requires-rehearsal")


def signing_preparation_before(before, after, environment="dev"):
    """Allow only the reviewed signing env addition while every process is stopped."""
    paused_connector(before)
    paused_connector(after)
    result = copy.deepcopy(before)
    expected = {
        "CONNECTOR_REQUIRE_SIGNING": {"value": "true"},
        "CONNECTOR_SIGNING_ENABLED": {"value": "true"},
        "CONNECTOR_SIGNING_ALGORITHM": {"value": "RS256"},
        "CONNECTOR_SIGNING_ISSUER": {"value": "farmer-partner"},
        "CONNECTOR_SIGNING_KEY_ID": {"value": "farmer-connector-v2-52da0fc34e90"},
        "CONNECTOR_SIGNING_PRIVATE_KEY_PEM": {"valueFrom": {"secretKeyRef": {"name": "farmer-connector-v2-signing", "key": "private-key.pem"}}},
    }
    if environment == "staging":
        expected["CONNECTOR_SIGNING_KEY_ID"] = {"value": "farmer-connector-v2-far"}
        expected["CONNECTOR_SIGNING_PRIVATE_KEY_PEM"] = {"valueFrom": {"secretKeyRef": {"name": "farmer-connector-v2-far-signing", "key": "private-key.pem"}}}
        expected["CONNECTOR_CELERY_QUEUE"] = {"value": "farmer-registry-connector-v2-far"}
        for document in after:
            if document["kind"] != "Deployment" or document["metadata"]["name"].endswith("-ui"):
                continue
            for container in pod(document).get("containers", []):
                env = {e["name"]: e for e in container.get("env", [])}
                required = dict(expected, CONNECTOR_DB_DBNAME={"value": "farmer_connector_v2_far"},
                                CONNECTOR_DB_USERNAME={"value": "far_farmer_connector_v2_user"},
                                CONNECTOR_DB_PASSWORD={"valueFrom": {"secretKeyRef": {"name": "farmer-connector-v2-far-db", "key": "password"}}})
                if any(env.get(k) != dict(name=k, **v) for k, v in required.items()):
                    raise ServiceError("staging-connector-isolation-or-signing-mismatch")
    newer = {(d["kind"], d["metadata"]["name"]): d for d in after}
    for document in result:
        if document["kind"] != "Deployment" or document["metadata"]["name"].endswith("-ui"):
            continue
        current = newer[(document["kind"], document["metadata"]["name"])]
        for old, new in zip(pod(document)["containers"], pod(current)["containers"]):
            env = {e["name"]: e for e in new.get("env", [])}
            if any(env.get(name) != dict(name=name, **value) for name, value in expected.items()):
                raise ServiceError("connector-signing-config-not-verified")
            existing = {e["name"] for e in old.get("env", [])}
            old.setdefault("env", []).extend(e for e in new["env"] if e["name"] in expected and e["name"] not in existing)
    return result


def guard_dashboard_api(before, after, image, namespace="farmer"):
    """An embedded API update may change only its image in the Registry release."""
    def index(items):
        result = {}
        for item in items:
            if item["kind"] == "Job":
                continue
            key = item["kind"], item["metadata"]["name"]
            if key in result or item["metadata"].get("namespace", namespace) != namespace:
                raise ServiceError("dashboard-api-resource-identity-changed")
            result[key] = copy.deepcopy(item)
        return result
    if any(item["kind"] == "Job" for item in after):
        raise ServiceError("dashboard-api-must-not-run-setup-jobs")
    old, new = index(before), index(after)
    key = "Deployment", "farmer-registry-dashboard-api"
    if set(old) != set(new) or key not in old:
        raise ServiceError("dashboard-api-existing-ownership-required")
    previous = pod(old[key]).get("containers", [])
    current = pod(new[key]).get("containers", [])
    if len(previous) != 1 or len(current) != 1 or current[0].get("image") != image:
        raise ServiceError("dashboard-api-pinned-image-required")
    current[0]["image"] = previous[0]["image"]
    if old != new:
        raise ServiceError("dashboard-api-would-change-unrelated-resources")


def isolated_connector(old, new, settings):
    def databases(manifest, variable):
        return {e.get("value") for d in manifest for c in pod(d).get("containers", [])
                for e in c.get("env", []) if e["name"] == variable}
    expected = settings.get("database")
    if not isinstance(expected, str) or not re.fullmatch(r"[a-z][a-z0-9_]+", expected):
        raise ServiceError("isolated-connector-database-required")
    old_names = databases(old, settings.get("oldDatabaseEnv"))
    new_names = databases(new, settings.get("databaseEnv"))
    if not old_names or any(not isinstance(name, str) or not name for name in old_names) or new_names != {expected} or expected in old_names:
        raise ServiceError("connector-database-isolation-unproven")
    def claims(manifest):
        names = {d["metadata"]["name"] for d in manifest if d["kind"] == "PersistentVolumeClaim"}
        names.update(v["persistentVolumeClaim"]["claimName"] for d in manifest
                     for v in pod(d).get("volumes", []) if "persistentVolumeClaim" in v)
        return names
    if claims(old) & claims(new):
        raise ServiceError("connector-storage-is-shared")


def artifact(component, record, registry):
    if not SHA.fullmatch(record.get("commit", "")) or not DIGEST.fullmatch(record.get("digest", "")):
        raise ServiceError("invalid-promotion-artifact")
    suffix = "-" + next(iter(image_specs(component))) if component.get("images") else ""
    if record.get("repository") != registry + "/" + component.get("imageRepository", "openg2p/" + component["name"] + suffix):
        raise ServiceError("promotion-repository-mismatch")
    expected_tag = record["commit"][:12]
    if record.get("overlayHashes"):
        expected_tag += "-" + hashlib.sha256(json.dumps(record["overlayHashes"], sort_keys=True).encode()).hexdigest()[:12]
    if record.get("tag") != expected_tag or not re.fullmatch(r"[0-9a-f]{64}", record.get("chartHash", "")):
        raise ServiceError("invalid-promotion-artifact")
    return record["repository"] + ":" + record["tag"] + "@" + record["digest"]


def image_artifacts(component, record, registry):
    primary = artifact(component, record, registry)
    if not component.get("images"):
        return {"main": primary}
    if set(record.get("images", {})) != set(component["images"]):
        raise ServiceError("missing-component-image-digest")
    images = {}
    for role in component["images"]:
        image = record["images"][role]
        if image.get("repository") != registry + "/openg2p/" + component["name"] + "-" + role or image.get("tag") != record["tag"] or not DIGEST.fullmatch(image.get("digest", "")):
            raise ServiceError("invalid-component-image-digest")
        images[role] = image["repository"] + ":" + image["tag"] + "@" + image["digest"]
    if next(iter(images.values())) != primary:
        raise ServiceError("primary-image-digest-mismatch")
    return images


def rehearsal(component, environment, record, overrides):
    path = ROOT / "helm/environments" / environment / "services/rehearsals" / (component["name"] + ".json")
    if not path.is_file():
        raise ServiceError("hook-rehearsal-required")
    review = json.loads(path.read_text(encoding="utf-8"))
    expected = {"commit": record["commit"], "digest": record["digest"],
                "chartHash": record["chartHash"], "environment": environment,
                "valuesHash": hashlib.sha256(json.dumps(overrides, sort_keys=True).encode()).hexdigest()}
    if any(review.get(k) != value for k, value in expected.items()):
        raise ServiceError("hook-rehearsal-artifact-mismatch")
    if review.get("isolatedDatabases") is not True or any(
        review.get(k) is not True for k in ("everyEnabledHook", "rerun", "failureRecovery")
    ):
        raise ServiceError("incomplete-hook-rehearsal")


def deploy(component, environment, record, source, registry, run=command):
    images = image_artifacts(component, record, registry)
    for role, spec in image_specs(component).items():
        if spec.get("overlay") and record.get("overlayHashes", {}).get(role) != chart_hash(relative_file(ROOT, spec["overlay"])):
            raise ServiceError("overlay-changed-since-build")
    checkout(component, environment, source, run, commit=record["commit"])
    _, chart = layout(component, source)
    if chart_hash(chart) != record["chartHash"]:
        raise ServiceError("promotion-chart-mismatch")
    # Every environment must have reviewed configuration. Missing config leaves
    # existing deployments untouched; defaults must never select a namespace/IdP.
    values_file = ROOT / "helm/environments" / environment / "services" / (component["name"] + ".yaml")
    if not values_file.is_file():
        raise SkipService("missing-environment-values")
    overrides = yaml.safe_load(values_file.read_text(encoding="utf-8")) or {}
    settings = overrides.pop("_coordination", {})
    if component.get("kind") == "connector":
        connector_settings(environment, settings)
        if environment == "staging":
            if not re.fullmatch(r"[0-9a-f]{64}", record.get("stagingBackupHash", "")):
                raise ServiceError("reviewed-staging-snapshot-required")
            settings["backupHash"] = record["stagingBackupHash"]
    release, namespace = component["release"], component["namespace"]
    embedded = component.get("kind") == "registry-dashboard-api"
    if settings.get("namespace") != namespace:
        raise ServiceError("environment-namespace-not-verified")
    args = ["-n", namespace]
    # A successful list returning no match is different from an auth/network
    # error. Never fall back to installation after helm status fails.
    matches = json.loads(run(["helm", "list", *args, "--all", "--filter", "^" + release + "$", "-o", "json"]))
    status = None
    if matches:
        status = json.loads(run(["helm", "status", release, *args, "-o", "json"]))
        if status.get("name") != release or status.get("namespace") != namespace or status.get("info", {}).get("status") != "deployed":
            raise ServiceError("existing-deployed-release-required")
        before = docs(run(["helm", "get", "manifest", release, *args]))
        values = yaml.safe_load(run(["helm", "get", "values", release, *args, "-o", "yaml"])) or {}
    else:
        if component.get("allowInstall") is not True:
            raise SkipService("no-existing-release")
        before, values = [], {}
    if component.get("kind") == "connector" and values.get("cossCutover", {}).get("phase") == "active":
        raise SkipService("active-connector-requires-accepted-image-rollout")
    merge(values, overrides)
    for role, spec in image_specs(component).items():
        selected = record["images"][role] if component.get("images") else record
        for value_path in spec["imageValues"]:
            target = values
            for part in value_path.split("."):
                target = target.setdefault(part, {})
            # OCI tag@digest works with existing repository:tag charts.
            target.update(repository=selected["repository"], tag=selected["tag"] + "@" + selected["digest"])
    with tempfile.TemporaryDirectory(prefix="registry-service-values-") as state:
        path = Path(state) / "values.yaml"
        path.write_text(yaml.safe_dump(values), encoding="utf-8")
        path.chmod(0o600)
        run(["helm", "repo", "add", "openg2p", "https://openg2p.github.io/openg2p-helm"])
        run(["helm", "dependency", "build", str(chart)])
        render_options = []
        if embedded:
            # The parent chart contains regular revision-named setup Jobs as
            # well as hooks. Suppress both for an API image-only deployment.
            renderer = Path(state) / "without-jobs"
            renderer.write_text("#!" + sys.executable + "\nimport sys,yaml\n"
                                "yaml.safe_dump_all([d for d in yaml.safe_load_all(sys.stdin) if d and d.get('kind') != 'Job'],sys.stdout)\n")
            renderer.chmod(0o700)
            render_options = ["--no-hooks", "--post-renderer", str(renderer)]
        after = docs(run(["helm", "template", release, str(chart), *args, "-f", str(path),
                          "--dry-run=server", *render_options, *(["--is-upgrade"] if status else [])]))
        guard_before = signing_preparation_before(before, after, environment) if component.get("kind") == "connector" else before
        if embedded:
            guard_dashboard_api(before, after, images["main"], namespace)
        else:
            guard(guard_before, after, namespace, images.values(), release)
        if component.get("kind") == "connector":
            from connector_cutover import verify_backup
            backup_dir = os.environ.get("CONNECTOR_BACKUP_DIRECTORY")
            if not backup_dir or not (Path(backup_dir) / "backup.json").is_file():
                raise ServiceError("connector-backup-required")
            if verify_backup(Path(backup_dir), environment) != settings.get("backupHash"):
                raise ServiceError("connector-backup-integrity-failed")
            old = docs(run(["helm", "get", "manifest", "farmer-connector", *args]))
            isolated_connector(old, after, settings)
            paused_connector(after)
        # New or changed hooks require an isolated rehearsal rather than running
        # unreviewed migrations/setup jobs during an optional image deployment.
        old_hooks = docs(run(["helm", "get", "hooks", release, *args])) if status and not embedded else []
        hooks = [d for d in after if d.get("metadata", {}).get("annotations", {}).get("helm.sh/hook")]
        if hooks or old_hooks:
            rehearsal(component, environment, record, overrides)
        if status:
            current = json.loads(run(["helm", "status", release, *args, "-o", "json"]))
            if (current.get("version"), current.get("info", {}).get("status")) != (status.get("version"), "deployed"):
                raise ServiceError("release-changed-during-preflight")
        elif json.loads(run(["helm", "list", *args, "--all", "--filter", "^" + release + "$", "-o", "json"])):
            raise ServiceError("release-appeared-during-preflight")
        run(["helm", "upgrade", release, str(chart), *args, "-f", str(path),
             *render_options, *(["--install"] if status is None else []), "--atomic", "--wait", "--wait-for-jobs", "--timeout", "10m"])
    final = json.loads(run(["helm", "status", release, *args, "-o", "json"]))
    if final.get("info", {}).get("status") != "deployed":
        raise ServiceError("release-not-deployed")
    final_manifest = docs(run(["helm", "get", "manifest", release, *args]))
    if embedded:
        guard_dashboard_api(before, final_manifest, images["main"], namespace)
    else:
        guard(signing_preparation_before(before, final_manifest, environment) if component.get("kind") == "connector" else before,
              final_manifest, namespace, images.values(), release)
    return final["version"]


def merge(target, overlay):
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def coordinate(components, action, environment, registry, previous, work, build_fn=build, deploy_fn=deploy):
    records = {}
    for component in components:
        name = component["name"]
        outcome = {"source": component["repository"], "branch": branch(environment, component),
                   "release": component["release"], "namespace": component["namespace"]}
        records[name] = outcome
        try:
            if action == "build":
                if environment == "staging" and component.get("kind") == "connector":
                    record = previous.get(name, {})
                    if record.get("outcome") != "deployed":
                        raise SkipService("connector-not-deployed-in-dev")
                    image_artifacts(component, record, registry)
                    record = {k: record[k] for k in ("commit", "repository", "tag", "digest", "chartHash", "images", "overlayHashes") if k in record}
                    if previous[name].get("stagingChartHash"):
                        record["devChartHash"] = record["chartHash"]
                        record["chartHash"] = previous[name]["stagingChartHash"]
                        record["stagingBackupHash"] = previous[name]["stagingBackupHash"]
                    record.update(promotedFromDev=True, devHelmRevision=previous[name]["helmRevision"])
                else:
                    record = build_fn(component, environment, work / name, registry)
                outcome.update(record, outcome="built")
            else:
                record = previous.get(name, {})
                if record.get("outcome") not in ("built", "deployed"):
                    raise SkipService("no-successful-build")
                if environment == "staging" and component.get("kind") == "connector":
                    if record.get("promotedFromDev") is not True or type(record.get("devHelmRevision")) is not int:
                        raise ServiceError("connector-not-promoted-from-dev")
                    outcome.update(promotedFromDev=True, devHelmRevision=record["devHelmRevision"])
                outcome.update({k: record[k] for k in ("commit", "repository", "tag", "digest", "chartHash", "images", "overlayHashes", "devChartHash", "stagingBackupHash") if k in record})
                outcome["helmRevision"] = deploy_fn(component, environment, record, work / name, registry)
                outcome["outcome"] = "deployed"
        except SkipService as error:
            outcome.update(getattr(error, "provenance", {}))
            outcome.update(outcome="skipped", reason=str(error))
        except ServiceError as error:
            outcome.update(error.provenance)
            outcome.update(outcome="failed", reason=str(error))
        except Exception:
            outcome.update(outcome="failed", reason="invalid-input-or-unexpected-tool-response")
        # Fixed, credential-free fields only. Never log exception/tool content.
        print(name + ": " + outcome["outcome"] + (" (" + outcome["reason"] + ")" if "reason" in outcome else ""))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "deploy"))
    parser.add_argument("--environment", choices=("dev", "staging"), required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--acceptance", type=Path, help="Dev acceptance evidence required for staging")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "deploy" and args.environment == "staging":
        validate_cluster("staging", os.environ.get("KUBECONFIG_CREDENTIAL"),
                         json.loads(command(["kubectl", "config", "view", "--minify", "-o", "json"])))
    if not re.fullmatch(r"\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com", args.registry):
        parser.error("Expected ap-south-1 ECR registry")
    previous = json.loads(args.input.read_text(encoding="utf-8")) if args.input else {}
    if args.action == "deploy" or args.environment == "staging":
        expected = "dev" if args.action == "build" or args.environment == "dev" else "staging"
        if previous.get("environment") != expected or previous.get("configHash") != configuration_hash():
            parser.error("Release requires the matching build/deployment manifest")
    if args.environment == "staging":
        if not args.acceptance:
            parser.error("Staging requires reviewed dev acceptance evidence")
        acceptance = json.loads(args.acceptance.read_text(encoding="utf-8"))
        required = ("freshLogin", "aweStatistics", "aweTaskList", "authorizedApproval",
                    "wrongIssuerRejected", "odkAttachments", "duplicatePrevention",
                    "registryIntake", "odkApproval", "dashboardHealth", "dashboardReporting",
                    "stagingIdentityVerified")
        if acceptance.get("configHash") != previous.get("configHash") or any(acceptance.get(k) is not True for k in required):
            parser.error("Dev acceptance or staging configuration verification incomplete")
        connectors = {c["name"] for c in configuration() if c.get("kind") == "connector"}
        for name, record in previous.get("components", {}).items():
            if name in connectors and record.get("outcome") in ("built", "deployed"):
                expected_digests = {role: image["digest"] for role, image in record["images"].items()} if record.get("images") else record.get("digest")
                if acceptance.get("images", {}).get(name) != expected_digests:
                    parser.error("Acceptance does not cover every promoted digest")
                staging = acceptance.get("staging", {})
                if (staging.get("namespace") != "far" or
                        not re.fullmatch(r"[0-9a-f]{64}", staging.get("connectorChartHash", "")) or
                        not re.fullmatch(r"[0-9a-f]{64}", staging.get("backupHash", ""))):
                    parser.error("Reviewed staging connector chart and final backup required")
                if args.action == "build":
                    record.update(stagingChartHash=staging["connectorChartHash"], stagingBackupHash=staging["backupHash"])
                elif record.get("chartHash") != staging["connectorChartHash"] or record.get("stagingBackupHash") != staging["backupHash"]:
                    parser.error("Staging connector rehearsal changed after promotion")
    with tempfile.TemporaryDirectory(prefix="registry-services-") as work:
        records = coordinate(configuration(environment=args.environment), args.action, args.environment, args.registry,
                             previous.get("components", {}), Path(work))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"environment": args.environment,
                                      "configHash": configuration_hash(),
                                      "components": records}, indent=2) + "\n", encoding="utf-8")
    return 2 if any(r["outcome"] == "failed" for r in records.values()) else 0


if __name__ == "__main__":
    # Lifecycle helpers import this module too; preserve the same error types
    # when the coordinator is launched directly as a script.
    sys.modules.setdefault("coordinator", sys.modules[__name__])
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, yaml.YAMLError):
        print("Invalid service configuration; private input withheld", file=sys.stderr)
        raise SystemExit(1)
