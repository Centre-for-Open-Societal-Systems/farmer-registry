#!/usr/bin/env python3
"""Private connector inventory and acceptance-gated retirement. Never deletes DBs.

Do not archive this tool's backup directory in Jenkins. Exports and dumps can
contain credentials and personal data. Retirement is a separate operator action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

from coordinator import command, docs, pod, ServiceError

OLD = "farmer-connector"
NEW = "farmer-registry-connector"
NAMESPACE = "farmer"
ACCEPTANCE = ("freshLogin", "aweStatistics", "aweTaskList", "authorizedApproval",
              "wrongIssuerRejected", "odkAttachments", "duplicatePrevention",
              "registryIntake", "odkApproval", "pipelinesAndMappingsMigrated",
              "checkpointsReconciled", "oldQueueDrained", "rollbackRehearsed",
              "sharedResourceOwnershipVerified")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(destination, exports, run=command):
    # Refuse reuse/overwrite: every inventory is immutable and independently kept.
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    status = json.loads(run(["helm", "status", OLD, "-n", NAMESPACE, "-o", "json"]))
    if status.get("name") != OLD or status.get("namespace") != NAMESPACE or status.get("info", {}).get("status") != "deployed":
        raise ServiceError("expected-old-deployed-release")
    files = {}
    for name, args in {
        "values.yaml": ["helm", "get", "values", OLD, "-n", NAMESPACE, "-o", "yaml"],
        "manifest.yaml": ["helm", "get", "manifest", OLD, "-n", NAMESPACE],
        "hooks.yaml": ["helm", "get", "hooks", OLD, "-n", NAMESPACE],
    }.items():
        path = destination / name
        path.write_text(run(args), encoding="utf-8")
        path.chmod(0o600)
        files[name] = sha(path)
    for name, source in exports.items():
        if not source.is_file() or source.stat().st_size == 0:
            raise ServiceError("missing-backup-export")
        path = destination / name
        shutil.copyfile(source, path)
        path.chmod(0o600)
        files[name] = sha(path)
    # pg_restore validates the supplied custom-format dump without a DB connection.
    run(["pg_restore", "--list", str(destination / "database.dump")])
    record = {"release": OLD, "namespace": NAMESPACE, "helmRevision": status["version"], "files": files}
    (destination / "backup.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def verify_backup(directory):
    record = json.loads((directory / "backup.json").read_text(encoding="utf-8"))
    required = {"values.yaml", "manifest.yaml", "hooks.yaml", "pipelines.json", "mappings.json", "checkpoints.json", "database.dump"}
    if set(record.get("files", {})) != required or record.get("release") != OLD or record.get("namespace") != NAMESPACE:
        raise ServiceError("incomplete-backup")
    if any(sha(directory / name) != digest for name, digest in record["files"].items()):
        raise ServiceError("backup-integrity-failed")
    return sha(directory / "backup.json")


def retirement_guard(manifest, workloads, new_status, new_manifest, acceptance, backup_hash):
    if new_status.get("name") != NEW or new_status.get("namespace") != NAMESPACE or new_status.get("info", {}).get("status") != "deployed":
        raise ServiceError("replacement-not-deployed")
    if acceptance.get("environment") != "dev" or acceptance.get("backupHash") != backup_hash:
        raise ServiceError("acceptance-backup-mismatch")
    if acceptance.get("helmRevision") != new_status.get("version"):
        raise ServiceError("replacement-changed-after-acceptance")
    if any(acceptance.get(k) is not True for k in ACCEPTANCE):
        raise ServiceError("acceptance-incomplete")
    digest = acceptance.get("digest", "")
    import re
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ServiceError("acceptance-digest-missing")
    images = [c.get("image", "") for d in new_manifest for c in pod(d).get("containers", [])
              if d["kind"] in ("Deployment", "StatefulSet")]
    if not images or not any(image.endswith("@" + digest) for image in images):
        raise ServiceError("accepted-image-not-deployed")
    # Helm uninstall deletes its owned objects; it must not own shared resources
    # or any unprotected storage. An external PostgreSQL DB is never dropped here.
    for d in manifest:
        metadata = d["metadata"]
        exact_route = d["kind"] == "VirtualService" and metadata["name"] == OLD
        if metadata.get("namespace", NAMESPACE) != NAMESPACE or not (metadata["name"].startswith(OLD + "-") or exact_route):
            raise ServiceError("old-release-contains-shared-resource")
        if d["kind"] in ("Namespace", "ClusterRole", "ClusterRoleBinding", "StatefulSet", "PersistentVolume"):
            raise ServiceError("old-release-contains-shared-or-database-resource")
        if d["kind"] == "PersistentVolumeClaim" and metadata.get("annotations", {}).get("helm.sh/resource-policy") != "keep":
            raise ServiceError("old-storage-not-retained")
        if d["kind"] not in ("Deployment", "Service", "Secret", "ConfigMap", "VirtualService", "Ingress",
                              "Job", "CronJob", "ServiceAccount", "Role", "RoleBinding", "PersistentVolumeClaim"):
            raise ServiceError("unknown-old-resource-kind")
    for d in workloads:
        if d["kind"] in ("Deployment", "StatefulSet") and (d["spec"].get("replicas", 1) or d.get("status", {}).get("replicas", 0)):
            raise ServiceError("old-workers-not-stopped")
        if d["kind"] == "CronJob" and d["spec"].get("suspend") is not True:
            raise ServiceError("old-scheduler-not-stopped")
        if d["kind"] == "DaemonSet" or d["kind"] == "Job" and d.get("status", {}).get("active", 0):
            raise ServiceError("old-jobs-not-drained")


def retire(directory, acceptance, run=command):
    backup_hash = verify_backup(directory)
    old_status = json.loads(run(["helm", "status", OLD, "-n", NAMESPACE, "-o", "json"]))
    saved = json.loads((directory / "backup.json").read_text(encoding="utf-8"))
    if (old_status.get("name"), old_status.get("namespace"), old_status.get("version")) != (OLD, NAMESPACE, saved.get("helmRevision")):
        raise ServiceError("old-release-changed-since-backup")
    old_manifest = docs(run(["helm", "get", "manifest", OLD, "-n", NAMESPACE]))
    old_hooks = docs(run(["helm", "get", "hooks", OLD, "-n", NAMESPACE]))
    # Uninstall hooks may delete a DB or shared resources even when the manifest
    # itself appears safe. No retirement hooks are allowed to run.
    if old_hooks:
        raise ServiceError("review-and-remove-retirement-hooks-first")
    workloads = []
    # Select by exact manifest names rather than optional app labels, which old
    # charts may omit or apply inconsistently.
    for d in old_manifest:
        if d["kind"] in ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"):
            workloads.append(json.loads(run(["kubectl", "get", d["kind"], d["metadata"]["name"],
                                             "-n", NAMESPACE, "-o", "json"])))
    selectors = [d.get("spec", {}).get("selector", {}).get("matchLabels", {}) for d in workloads]
    live_pods = json.loads(run(["kubectl", "get", "pods", "-n", NAMESPACE, "-o", "json"]))["items"]
    for p in live_pods:
        metadata = p["metadata"]
        owned = metadata["name"].startswith(OLD + "-") or any(
            selector and all(metadata.get("labels", {}).get(k) == v for k, v in selector.items())
            for selector in selectors)
        if owned and p.get("status", {}).get("phase") not in ("Succeeded", "Failed"):
            raise ServiceError("old-pods-not-stopped")
    status = json.loads(run(["helm", "status", NEW, "-n", NAMESPACE, "-o", "json"]))
    new_manifest = docs(run(["helm", "get", "manifest", NEW, "-n", NAMESPACE]))
    retirement_guard(old_manifest, workloads, status, new_manifest, acceptance, backup_hash)
    for name, previous in ((OLD, old_status), (NEW, status)):
        current = json.loads(run(["helm", "status", name, "-n", NAMESPACE, "-o", "json"]))
        if (current.get("version"), current.get("info", {}).get("status")) != (previous.get("version"), "deployed"):
            raise ServiceError("release-changed-during-retirement")
    run(["helm", "uninstall", OLD, "-n", NAMESPACE, "--no-hooks", "--keep-history", "--wait", "--timeout", "5m"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    save = sub.add_parser("backup")
    save.add_argument("--directory", type=Path, required=True)
    for name in ("pipelines", "mappings", "checkpoints", "database"):
        save.add_argument("--" + name, type=Path, required=True)
    remove = sub.add_parser("retire")
    remove.add_argument("--directory", type=Path, required=True)
    remove.add_argument("--acceptance", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "backup":
        backup(args.directory, {"pipelines.json": args.pipelines, "mappings.json": args.mappings,
                                "checkpoints.json": args.checkpoints, "database.dump": args.database})
        print("PASS: private inventory saved; copy backups to retained storage")
    else:
        retire(args.directory, json.loads(args.acceptance.read_text()))
        print("PASS: old connector uninstalled; database, retained storage and backups preserved")


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Exception:
        print("FAIL: connector action stopped; private output withheld", file=sys.stderr)
        raise SystemExit(1)
