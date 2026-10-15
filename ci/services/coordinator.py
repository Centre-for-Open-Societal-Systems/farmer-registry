#!/usr/bin/env python3
"""Build optional services independently, promote digests, preserve release ownership.

Private subprocess output and release values never enter the outcome artifact.
Exit 2 means optional failures (Jenkins UNSTABLE); configuration errors exit 1.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "ci/services/components.yaml"
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


def configuration(path=MANIFEST):
    items = yaml.safe_load(path.read_text(encoding="utf-8"))["components"]
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
        if item["release"] in ("commons", "commons-services", "farmer-connector", "farmer-registry"):
            raise ValueError("Optional service must not adopt an existing shared/Registry/old connector release")
    return items


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
    chart = relative_file(source, component["chart"])
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
    repository = registry + "/openg2p/" + component["name"] + suffix
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
        if (overlay / "test_media.py").is_file():
            run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "python",
                 "-v", str(overlay / "test_media.py") + ":/tests/test_media.py:ro", image, "/tests/test_media.py"])
        if (overlay / "rehearse.py").is_file():
            rehearsal_result = json.loads(run([sys.executable, str(overlay / "rehearse.py"), image]).strip().splitlines()[-1])
            if not all(rehearsal_result.get(name) is True for name in ("schemaRerun", "failedDdlRolledBack", "failureRecovery", "duplicateSentOnce", "pollTimestampPersisted", "isolatedDatabases")):
                raise ServiceError("connector-schema-rehearsal-failed")
    pushed = run(["docker", "push", image])
    matches = re.findall(r"digest: (sha256:[0-9a-f]{64})\b", pushed)
    if len(set(matches)) != 1:
        raise ServiceError("missing-pushed-digest")
    digest = matches[0]
    published = run(["aws", "ecr", "describe-images", "--region", "ap-south-1",
                  "--repository-name", "openg2p/" + component["name"] + suffix,
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
    if record.get("repository") != registry + "/openg2p/" + component["name"] + suffix:
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
    path = ROOT / "ci/services" / environment / "rehearsals" / (component["name"] + ".json")
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
    values_file = ROOT / "ci/services" / environment / (component["name"] + ".yaml")
    if not values_file.is_file():
        raise SkipService("missing-environment-values")
    overrides = yaml.safe_load(values_file.read_text(encoding="utf-8")) or {}
    settings = overrides.pop("_coordination", {})
    release, namespace = component["release"], component["namespace"]
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
        run(["helm", "dependency", "build", str(chart)])
        after = docs(run(["helm", "template", release, str(chart), *args, "-f", str(path),
                          "--dry-run=server", *(["--is-upgrade"] if status else [])]))
        guard(before, after, namespace, images.values(), release)
        if component.get("kind") == "connector":
            from connector_cutover import verify_backup
            backup_dir = os.environ.get("CONNECTOR_BACKUP_DIRECTORY")
            if not backup_dir or verify_backup(Path(backup_dir)) != settings.get("backupHash"):
                raise ServiceError("connector-backup-required")
            old = docs(run(["helm", "get", "manifest", "farmer-connector", *args]))
            isolated_connector(old, after, settings)
            paused_connector(after)
        # New or changed hooks require an isolated rehearsal rather than running
        # unreviewed migrations/setup jobs during an optional image deployment.
        old_hooks = docs(run(["helm", "get", "hooks", release, *args])) if status else []
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
             *(["--install"] if status is None else []), "--atomic", "--wait", "--wait-for-jobs", "--timeout", "10m"])
    final = json.loads(run(["helm", "status", release, *args, "-o", "json"]))
    if final.get("info", {}).get("status") != "deployed":
        raise ServiceError("release-not-deployed")
    guard(before, docs(run(["helm", "get", "manifest", release, *args])), namespace, images.values(), release)
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
                outcome.update({k: record[k] for k in ("commit", "repository", "tag", "digest", "chartHash", "images", "overlayHashes") if k in record})
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
    if not re.fullmatch(r"\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com", args.registry):
        parser.error("Expected ap-south-1 ECR registry")
    previous = json.loads(args.input.read_text(encoding="utf-8")) if args.input else {}
    if args.action == "deploy" or args.environment == "staging":
        expected = "dev" if args.action == "build" or args.environment == "dev" else "staging"
        if previous.get("environment") != expected or previous.get("configHash") != hashlib.sha256(MANIFEST.read_bytes()).hexdigest():
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
    with tempfile.TemporaryDirectory(prefix="registry-services-") as work:
        records = coordinate(configuration(), args.action, args.environment, args.registry,
                             previous.get("components", {}), Path(work))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"environment": args.environment,
                                      "configHash": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
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
