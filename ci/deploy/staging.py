"""Fail closed unless trusted rehearsal evidence covers this exact staging rollout.

Bind this file through Jenkins staging-farmer-rehearsal, never a build parameter
or an artifact downloaded from an untrusted PR. Evidence contains no credentials.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
from environments import configuration, validate_cluster

SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
HASH = re.compile(r"[0-9a-f]{64}")
REHEARSAL = (
    "registryDumpRestored", "connectorDumpRestored", "backupChecksumsVerified",
    "coordinateConversion36", "documentHistoryEventType", "applicationMigrations",
    "metadataSeeding", "reporting", "everyEnabledHook", "migrationRerun",
    "injectedFailureRecovery", "manifestPreservation", "geographyExactMatch",
    "canonicalMediaVersionRehearsed", "existingSubmissionsPreserved",
    "farmerPartnerRegistered", "partnerRoutingAndKeys", "stagingStaffIssuer",
    "internalStaffJwks", "signatureVerificationEnabled", "registryRuntimeTests",
    "connectorRuntimeTests", "commonsFarmerPrerequisites", "isolatedDatabases",
)
CUTOVER = ("farmerMaintenance", "farmerWritersPaused", "legacyIngestionStopped",
           "oldQueueDrained", "finalBackupsVerified", "schemaMigrationComplete")
ACCEPTANCE = ("freshLogin", "aweStatistics", "aweTaskList", "syntheticWebRegistered",
              "syntheticSignedOdkRegistered", "collectorAttribution", "attachments",
              "retries", "duplicatePrevention", "authorizedApproval", "wrongIssuerRejected",
              "unsignedRejected", "tamperedRejected", "expiredRejected", "wrongKeyRejected",
              "realSubmissionPending", "checkpointReconciled", "singleScheduler",
              "automaticPollNoDuplicates", "temporaryResourcesExportedAndRemoved")


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def manifest_hash(documents):
    # Hook/revision Jobs are checked separately by everyEnabledHook rehearsal.
    # Bind every persistent resource body, including routing and Secret data,
    # without depending on generated release metadata or list order.
    resources = []
    for doc in documents:
        if doc["kind"] == "Job" or doc.get("metadata", {}).get("annotations", {}).get("helm.sh/hook"):
            continue
        resources.append({"kind": doc["kind"], "name": doc["metadata"]["name"],
                          "namespace": doc["metadata"].get("namespace", "far"),
                          "body": {k: v for k, v in doc.items() if k not in ("apiVersion", "kind", "metadata", "status")}})
    return content_hash(sorted(resources, key=lambda r: (r["kind"], r["name"])))


def delivery_hash(root=ROOT):
    """Bind code, chart, migrations and overlays; omit downloads and local output."""
    result = hashlib.sha256()
    for directory in ("ci", "helm", "scripts", "integrations", "docker", "farmer-extension", "tests/runtime"):
        for path in sorted((root / directory).rglob("*")):
            relative = path.relative_to(root)
            if not path.is_file() or {"charts", "__pycache__", ".pytest_cache", ".venv"}.intersection(relative.parts):
                continue
            result.update(relative.as_posix().encode() + b"\0")
            # Git uses LF on Jenkins; permit Windows review of the same tree.
            result.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return result.hexdigest()


def passed(record, names):
    if any(record.get(name) is not True for name in names):
        raise ValueError("Staging evidence has incomplete verification")


def evidence(path, source_commit, now=None):
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if record.get("environment") != "staging" or record.get("namespace") != "far" or record.get("platform") != "1.2.2-rc.544":
        raise ValueError("Staging evidence environment/platform mismatch")
    if not SHA.fullmatch(source_commit) or record.get("deliveryHash") != delivery_hash():
        raise ValueError("Staging delivery changed after rehearsal")
    current = now or datetime.now(timezone.utc)
    verified = datetime.fromisoformat(record["verifiedAt"].replace("Z", "+00:00"))
    if verified.tzinfo is None or not timedelta(0) <= current - verified <= timedelta(hours=24):
        raise ValueError("Staging rehearsal evidence is stale or future dated")
    passed(record.get("rehearsal", {}), REHEARSAL)
    registry = record["registry"]
    if not re.fullmatch(r"\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com", registry.get("registry", "")):
        raise ValueError("Staging image registry is invalid")
    if not SHA.fullmatch(registry.get("sourceCommit", "")):
        raise ValueError("Registry source provenance required")
    required = {"staff-api", "staff-ui", "partner-api", "celery", "db-seed", "sanity-tests"}
    if set(registry.get("images", {})) != required:
        raise ValueError("Complete tested Registry image set required")
    for component, image in registry["images"].items():
        if (not SHA.fullmatch(image.get("sourceCommit", "")) or image.get("tag") != image["sourceCommit"][:12]
                or not DIGEST.fullmatch(image.get("digest", ""))
                or image.get("repository") != registry["registry"] + "/openg2p/farmer-registry/" + component
                or image.get("runtimeTested") is not True):
            raise ValueError("Unverified Registry image provenance")
        registry["images"][component] = {k: image[k] for k in ("repository", "tag", "sourceCommit", "digest", "runtimeTested")}
    record["registry"] = {k: registry[k] for k in ("registry", "sourceCommit", "images")}
    # A hash alone does not establish a restore. Both restored database evidence
    # and retained, checksummed exports are mandatory.
    required_backups = {"registry", "connector", "helm", "odkFormMedia", "pipelines", "runHistory", "checkpoints"}
    backups = record.get("backups", {})
    if set(backups) != required_backups or any(not HASH.fullmatch(v) for v in backups.values()):
        raise ValueError("Complete protected staging backup inventory required")
    if type(record.get("baselineRevision")) is not int or record["baselineRevision"] < 1:
        raise ValueError("Staging baseline revision required")
    if not all(HASH.fullmatch(record.get(k, "")) for k in ("valuesHash", "manifestHash", "candidateManifestHash")):
        raise ValueError("Staging baseline content hashes required")
    return record


def cutover(record, status, values, manifest, now=None):
    passed(record.get("cutover", {}), CUTOVER)
    current = now or datetime.now(timezone.utc)
    final = datetime.fromisoformat(record["finalBackupAt"].replace("Z", "+00:00"))
    if final.tzinfo is None or not timedelta(0) <= current - final <= timedelta(hours=1):
        raise ValueError("Fresh final maintenance backup required")
    if (status.get("name"), status.get("namespace"), status.get("version"), status.get("info", {}).get("status")) != (
            "farmer-registry", "far", record["baselineRevision"], "deployed"):
        raise ValueError("Staging release changed after rehearsal")
    if content_hash(values) != record["valuesHash"] or content_hash(manifest) != record["manifestHash"]:
        raise ValueError("Staging values/manifests changed after rehearsal")
    if values.get("global", {}).get("registryDB") != configuration("staging")["registryDatabase"]:
        raise ValueError("Staging Registry database mismatch")


def main():
    action, *args = sys.argv[1:]
    if action == "template":
        # False/empty defaults can never authorize deployment. Operators attach
        # measured evidence after rehearsal; this command performs no API calls.
        record = {"environment": "staging", "namespace": "far", "platform": "1.2.2-rc.544",
                  "deliveryHash": delivery_hash(), "verifiedAt": "", "finalBackupAt": "",
                  "baselineRevision": None, "valuesHash": "", "manifestHash": "", "candidateManifestHash": "",
                  "rehearsal": dict.fromkeys(REHEARSAL, False), "cutover": dict.fromkeys(CUTOVER, False),
                  "backups": dict.fromkeys(("registry", "connector", "helm", "odkFormMedia", "pipelines", "runHistory", "checkpoints"), ""),
                  "registry": {"registry": "", "sourceCommit": "", "images": {
                      name: {"repository": "", "tag": "", "sourceCommit": "", "digest": "", "runtimeTested": False}
                      for name in ("staff-api", "staff-ui", "partner-api", "celery", "db-seed", "sanity-tests")}}}
        with Path(args[0]).open("x", encoding="utf-8") as output:
            json.dump(record, output, indent=2)
            output.write("\n")
        print("Created unverified staging evidence template; deployment remains blocked")
        return
    if action == "cluster":
        validate_cluster("staging", os.environ.get("KUBECONFIG_CREDENTIAL"), json.loads(Path(args[0]).read_text()))
        return
    record = evidence(os.environ["STAGING_EVIDENCE_FILE"], os.environ["SOURCE_COMMIT"])
    if action == "cutover":
        status, values = (json.loads(Path(p).read_text()) for p in args[:2])
        manifest = [d for d in yaml.safe_load_all(Path(args[2]).read_text()) if isinstance(d, dict)]
        cutover(record, status, values, manifest)
    elif action == "summary":
        Path(args[0]).write_text(json.dumps({k: record[k] for k in (
            "environment", "namespace", "platform", "deliveryHash", "verifiedAt", "baselineRevision", "registry", "backups")}, indent=2) + "\n")
    elif action != "verify":
        raise ValueError("Unknown staging evidence operation")
    print("PASS: staging rehearsal " + action)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("FAIL: staging evidence rejected; private input withheld", file=sys.stderr)
        raise SystemExit(1)
