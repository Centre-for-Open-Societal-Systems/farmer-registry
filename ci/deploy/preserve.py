"""Durable preserving-adoption protocol. No database reset operation exists."""
from __future__ import annotations

import hashlib
import json
import re
import uuid

CLUSTER = "a842b14f-b29f-4e78-b9d2-bfb22a17e53a"
ROLES = {"staff-api", "partner-api", "celery", "db-seed", "sanity-tests", "staff-ui"}
STATES = ("PLANNED", "PAUSED", "BACKED_UP", "NATIVE_READY", "UPGRADED", "ACCEPTED", "VERIFIED")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(config):
    require(config.get("mode") == "preserving-upgrade", "Preserving mode required")
    require((config.get("clusterUid"), config.get("namespace"), config.get("release"), config.get("database"))
            == (CLUSTER, "farmer", "farmer-registry", "farmer_registry"), "Exact New Dev Farmer target required")
    require(re.fullmatch(r"[a-f0-9]{40}", config.get("sourceCommit", "")), "Immutable source required")
    require(config.get("chartVersion") == "1.0.0-dev.16"
            and re.fullmatch(r"[a-f0-9]{64}", config.get("chartSha256", "")), "Reviewed chart required")
    require(set(config.get("images", {})) == ROLES, "All six immutable images required")
    for role, image in config["images"].items():
        require(re.fullmatch(r"\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com/openg2p/farmer-registry/"
                             + re.escape(role) + ":" + config["sourceCommit"][:12] + r"@sha256:[a-f0-9]{64}", image),
                "Image source/repository/digest mismatch")
    require(config.get("expectedRevision", 0) > 0 and type(config["expectedRevision"]) is int, "Expected Helm revision required")


def fingerprint(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def adopt(config, store, actions, *, initialize=False, resume=False):
    """CAS lock, pause, restore-tested backup, native upgrade, controlled resume.

    Stage operations are idempotent and retain their private subreceipts. A lost
    lease never resumes writers. An ambiguous Helm result requires its own
    revision/read-back recovery, never an automatic rollback or blind retry.
    """
    validate(config)
    store.check_cluster()
    version, receipt = store.read()
    key = fingerprint(config)
    if receipt is None:
        require(initialize and not resume, "Explicit initialization required")
        actions.preflight(config)
        receipt = {**config, "fingerprint": key, "state": "PLANNED", "lock": None,
                   "backupVerified": False, "originalBusinessPreserved": False}
        version = store.cas(None, receipt)
    require(receipt.get("fingerprint") == key and receipt.get("state") in STATES, "Adoption identity/state mismatch")
    require(receipt.get("lock") is None, "Adoption is locked; confirm prior owner stopped before recovery")
    if receipt["state"] == "VERIFIED":
        actions.verify_installed(config)
        return receipt
    require(resume or receipt["state"] == "PLANNED", "Interrupted adoption requires explicit resume")
    receipt = {**receipt, "lock": uuid.uuid4().hex}
    version = store.cas(version, receipt)
    owner = receipt["lock"]

    def save(state, **extra):
        nonlocal receipt, version
        receipt = {**receipt, **extra, "state": state}
        version = store.cas(version, receipt)

    try:
        if receipt["state"] == "PLANNED":
            # Save exact UIDs/replicas before the first scale or controller edit.
            if "workloads" not in receipt:
                save("PLANNED", workloads=actions.snapshot(config))
            actions.pause(receipt["workloads"])
            save("PAUSED")
        actions.assert_paused(receipt["workloads"])
        if receipt["state"] == "PAUSED":
            backup = actions.backup(config)
            actions.verify_backup(backup)
            save("BACKED_UP", backup=backup, backupVerified=True)
        actions.verify_backup(receipt["backup"])
        if receipt["state"] == "BACKED_UP":
            actions.native_migrate(config)
            actions.native_seed(config)
            actions.verify_preservation(config)
            save("NATIVE_READY", originalBusinessPreserved=True, expiresAt=actions.expires_at())
        if receipt["state"] == "NATIVE_READY":
            actions.assert_paused(receipt["workloads"])
            actions.verify_preservation(config)
            save("NATIVE_READY", expiresAt=actions.expires_at())
            actions.upgrade(config, receipt)
            save("UPGRADED")
        if receipt["state"] == "UPGRADED":
            actions.verify_installed(config)
            actions.accept(config)
            save("ACCEPTED")
        if receipt["state"] == "ACCEPTED":
            actions.resume(receipt["workloads"])
            save("VERIFIED", expiresAt=0)
        return receipt
    except Exception:
        # A native/Helm/acceptance failure must not silently resume producers.
        # Retry must prove the same UIDs and backup rather than starting over.
        current_version, current = store.read()
        if current_version == version and current.get("lock") == owner and receipt.get("workloads"):
            actions.pause(receipt["workloads"])
        raise
    finally:
        current_version, current = store.read()
        if current_version == version and current.get("lock") == owner:
            store.cas(version, {**current, "lock": None})
