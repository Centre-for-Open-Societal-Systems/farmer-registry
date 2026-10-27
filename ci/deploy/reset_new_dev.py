"""Guarded, one-epoch registry rebuild. Never runs during import or planning.

The pipeline owns reviewed native migration/seed/acceptance commands. This helper
owns target checks, durable CAS receipts, backup/restore rehearsal and DB reset.
It deliberately cannot auto-resume an ambiguous RESET_STARTED state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import uuid
from pathlib import Path

STATES = (
    "PLANNED",
    "BACKED_UP",
    "QUIESCED",
    "RESET_STARTED",
    "DB_CREATED",
    "SEEDED",
    "ACCEPTED",
    "VERIFIED",
)
NAMESPACES = {"farmer": "farmer", "crop": "crop", "livestock": "livestock"}
FORBIDDEN = (
    "commons",
    "keycloak",
    "master",
    "consent",
    "partner",
    "document",
    "template",
    "postgres",
    "iam",
    "awe",
)


class Refused(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise Refused(message)


def identifier(value):
    require(
        isinstance(value, str) and re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value),
        "Invalid SQL identifier",
    )
    return '"' + value + '"'


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def fingerprint(config):
    return hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate(config):
    require(
        config.get("version") == 1 and config.get("environment") == "new-dev",
        "Only New Dev v1 manifests are accepted",
    )
    target = config.get("target", {})
    require(target.get("registry") in NAMESPACES, "Registry is not allowlisted")
    require(
        target.get("namespace") == NAMESPACES[target["registry"]],
        "Registry namespace mismatch",
    )
    for key in (
        "context",
        "cluster_uid",
        "release",
        "database",
        "owner",
        "database_server_address",
    ):
        require(
            isinstance(target.get(key), str)
            and target[key]
            and "REVIEW" not in target[key],
            "Incomplete reviewed target",
        )
    require(
        not any(
            word in target["context"].lower() for word in ("staging", "production")
        ),
        "Non-dev context refused",
    )
    identifier(target["database"])
    identifier(target["owner"])
    require(
        isinstance(target.get("database_server_port"), int)
        and 0 < target["database_server_port"] < 65536,
        "Exact database server port required",
    )
    require(
        not any(word in target["database"].lower() for word in FORBIDDEN),
        "Shared/system database refused",
    )
    require(
        config.get("allowlist") == [target],
        "Exactly one matching reviewed target is required",
    )
    require(
        re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", config.get("epoch", "")),
        "Invalid reset epoch",
    )
    require(
        config.get("source_commit")
        and re.fullmatch(r"[0-9a-f]{40}", config["source_commit"]),
        "Source commit must be pinned",
    )
    require(
        config.get("chart")
        and all(
            "@sha256:" in value and re.search(r"@sha256:[0-9a-f]{64}$", value)
            for value in config.get("images", {}).values()
        )
        and len(config.get("images", {})) >= 5,
        "Image/chart locks incomplete",
    )
    require(
        config.get("workloads")
        and len(set(config["workloads"])) == len(config["workloads"]),
        "Exact target workloads required",
    )
    for resource in config["workloads"]:
        require(
            re.fullmatch(r"(?:deployment|statefulset)/[a-z0-9][a-z0-9-]*", resource),
            "Only exact target workload names are accepted",
        )
    controlled = config.get("verification_workloads")
    require(
        isinstance(controlled, list)
        and controlled
        and len(set(controlled)) == len(controlled)
        and set(controlled) < set(config["workloads"]),
        "Verification workloads must be an explicit proper subset; producers stay paused",
    )
    for stage in (
        "snapshot",
        "migrate",
        "seed",
        "verify",
        "pause_producers",
        "assert_producers_paused",
        "resume_producers",
    ):
        command = config.get("commands", {}).get(stage)
        require(
            isinstance(command, list)
            and command
            and all(isinstance(x, str) and x for x in command),
            "Native command missing: " + stage,
        )
        require(
            Path(command[0]).name in {"kubectl", "helm", "python3", "python"},
            "Unreviewed command launcher",
        )
        require(
            not any(
                re.search(r"(?:password|token|secret)=", x, re.IGNORECASE)
                for x in command
            ),
            "Inline credentials refused",
        )
    require(
        config.get("protected_directory")
        and Path(config["protected_directory"]).is_absolute(),
        "Protected artifact directory required",
    )
    return target


def command(argv, *, stdin=None, env=None):
    """Never echo commands, credentials, or child stdout/stderr on failure."""
    try:
        result = subprocess.run(
            argv,
            input=stdin,
            text=True,
            capture_output=True,
            env=env,
            check=False,
            timeout=1800,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise Refused("Required deployment executable is unavailable") from None
    require(
        result.returncode == 0,
        "Deployment command failed; inspect protected pipeline diagnostics",
    )
    return result.stdout


class ConfigMapStore:
    """Namespace ConfigMap, created once and replaced with resourceVersion CAS.

    No TTL lock stealing: an interrupted holder must be confirmed stopped and
    its lock released by reviewed recovery administration before resume.
    """

    def __init__(self, config):
        self.target = config["target"]
        # Registry-stable name prevents changing epoch from creating a second
        # independent receipt and silently authorizing another first-install reset.
        self.name = "registry-reset-" + config["target"]["registry"]
        self.prefix = [
            "kubectl",
            "--context",
            self.target["context"],
            "-n",
            self.target["namespace"],
        ]

    def check_cluster(self):
        uid = command(
            self.prefix
            + ["get", "namespace", "kube-system", "-o", "jsonpath={.metadata.uid}"]
        ).strip()
        require(uid == self.target["cluster_uid"], "Cluster identity mismatch")
        namespace = json.loads(
            command(
                self.prefix
                + ["get", "namespace", self.target["namespace"], "-o", "json"]
            )
        )
        require(
            namespace["metadata"]["name"] == self.target["namespace"],
            "Namespace identity mismatch",
        )

    def read(self):
        raw = command(
            self.prefix
            + ["get", "configmap", self.name, "--ignore-not-found", "-o", "json"]
        )
        if not raw.strip():
            return None, None
        obj = json.loads(raw)
        return obj["metadata"]["resourceVersion"], json.loads(
            obj["data"]["receipt.json"]
        )

    def cas(self, version, receipt):
        obj = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": self.name, "namespace": self.target["namespace"]},
            "data": {"receipt.json": json.dumps(receipt, sort_keys=True)},
        }
        if version is not None:
            obj["metadata"]["resourceVersion"] = version
        # A create conflict or stale replace fails closed; no force/apply fallback.
        raw = command(
            self.prefix
            + ["create" if version is None else "replace", "-f", "-", "-o", "json"],
            stdin=json.dumps(obj),
        )
        return json.loads(raw)["metadata"]["resourceVersion"]


class Actions:
    def __init__(self, config, store, admin_service):
        self.config, self.store = config, store
        self.target = config["target"]
        self.directory = Path(config["protected_directory"])
        self.admin_service = admin_service

    def db(self):
        import psycopg2

        # libpq service/password files are mounted by CI, never in the manifest.
        connection = psycopg2.connect(service=self.admin_service, dbname="postgres")
        connection.autocommit = True
        return connection

    def sql(self, query, values=None):
        connection = self.db()
        try:
            # psycopg2's connection context starts a transaction even when
            # autocommit is set; CREATE/DROP DATABASE must stay outside one.
            with connection.cursor() as cursor:
                cursor.execute(query, values)
                return cursor.fetchall() if cursor.description else []
        finally:
            connection.close()

    def check_database(self, *, absent_ok=False):
        server = self.sql("SELECT inet_server_addr()::text, inet_server_port()")
        require(
            server
            == [
                (
                    self.target["database_server_address"],
                    self.target["database_server_port"],
                )
            ],
            "Database server identity mismatch",
        )
        rows = self.sql(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s",
            (self.target["database"],),
        )
        require(
            absent_ok and not rows or rows == [(self.target["owner"],)],
            "Database/owner identity mismatch",
        )
        return bool(rows)

    def protected(self):
        require(
            self.directory.is_dir() and not self.directory.is_symlink(),
            "Protected directory must already exist",
        )
        require(
            stat.S_IMODE(self.directory.stat().st_mode) & 0o077 == 0,
            "Artifact directory must be owner-only",
        )

    def backup(self):
        self.protected()
        path = self.directory / (self.config["epoch"] + ".dump")
        # Preserve an interrupted backup for inspection; never overwrite it.
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        env = {**os.environ, "PGSERVICE": self.admin_service}
        command(
            [
                "pg_dump",
                "--format=custom",
                "--file",
                str(path),
                "--dbname",
                self.target["database"],
            ],
            env=env,
        )
        command(["pg_restore", "--list", str(path)], env=env)
        rehearsal = "registry_restore_" + uuid.uuid4().hex
        self.sql(
            "CREATE DATABASE "
            + identifier(rehearsal)
            + " OWNER "
            + identifier(self.target["owner"])
        )
        try:
            command(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--dbname",
                    rehearsal,
                    str(path),
                ],
                env=env,
            )
        finally:
            # Only this invocation's generated scratch database can be removed.
            require(
                re.fullmatch(r"registry_restore_[0-9a-f]{32}", rehearsal),
                "Invalid rehearsal identity",
            )
            self.sql("DROP DATABASE " + identifier(rehearsal))
        require(path.stat().st_size > 0, "Empty backup")
        self.run_native("snapshot")
        snapshot = self.directory / (self.config["epoch"] + ".snapshot.json")
        require(
            snapshot.is_file() and not snapshot.is_symlink(),
            "Recovery configuration snapshot missing",
        )
        require(
            stat.S_IMODE(snapshot.stat().st_mode) & 0o077 == 0,
            "Recovery snapshot must be owner-only",
        )
        return {
            "sha256": digest(path),
            "bytes": path.stat().st_size,
            "snapshot_sha256": digest(snapshot),
            "restore_verified": True,
        }

    def verify_backup(self, backup):
        self.protected()
        path = self.directory / (self.config["epoch"] + ".dump")
        snapshot = self.directory / (self.config["epoch"] + ".snapshot.json")
        require(
            not path.is_symlink()
            and path.is_file()
            and stat.S_IMODE(path.stat().st_mode) & 0o077 == 0,
            "Protected backup missing",
        )
        require(
            snapshot.is_file()
            and not snapshot.is_symlink()
            and stat.S_IMODE(snapshot.stat().st_mode) & 0o077 == 0,
            "Protected snapshot missing",
        )
        require(
            backup.get("restore_verified") is True
            and backup.get("sha256") == digest(path)
            and backup.get("bytes") == path.stat().st_size
            and backup.get("snapshot_sha256") == digest(snapshot),
            "Backup evidence mismatch",
        )

    def workload_snapshot(self):
        result = {}
        for resource in self.config["workloads"]:
            obj = json.loads(
                command(self.store.prefix + ["get", resource, "-o", "json"])
            )
            require(
                obj["metadata"].get("labels", {}).get("app.kubernetes.io/instance")
                == self.target["release"],
                "Workload release ownership mismatch",
            )
            require(
                obj["metadata"]["namespace"] == self.target["namespace"],
                "Workload namespace mismatch",
            )
            result[resource] = {
                "uid": obj["metadata"]["uid"],
                "replicas": obj["spec"].get("replicas", 1),
            }
        return result

    def preflight(self):
        """Inspect all namespace controllers that could defeat exact target drain.

        Namespace-wide HPA/Jobs are checked against target workload owners too,
        since separately managed controllers may lack the Helm release label.
        This is read-only; operators must pause controllers through reviewed
        deployment handling. No automatic HPA deletion or CronJob patching.
        """
        self.store.check_cluster()
        self.run_native("assert_producers_paused")
        self.workload_snapshot()
        target_names = {item.split("/", 1)[1] for item in self.config["workloads"]}
        selector = "app.kubernetes.io/instance"

        def owned(obj):
            metadata = obj.get("metadata", {})
            return metadata.get("labels", {}).get(selector) == self.target[
                "release"
            ] or any(
                owner.get("name") in target_names
                for owner in metadata.get("ownerReferences", [])
            )

        for kind in ("horizontalpodautoscalers", "cronjobs", "jobs"):
            items = json.loads(
                command(self.store.prefix + ["get", kind, "-o", "json"])
            )["items"]
            for obj in items:
                if kind == "horizontalpodautoscalers":
                    relevant = (
                        owned(obj)
                        or obj.get("spec", {}).get("scaleTargetRef", {}).get("name")
                        in target_names
                    )
                    require(
                        not relevant,
                        "Target HPA can undo drain; reviewed controller pause is required",
                    )
                elif kind == "cronjobs":
                    require(
                        not owned(obj) or obj.get("spec", {}).get("suspend") is True,
                        "Target CronJob is not suspended",
                    )
                else:
                    require(
                        not owned(obj) or not obj.get("status", {}).get("active", 0),
                        "Target Job is still active",
                    )
        return {
            "cluster_uid": self.target["cluster_uid"],
            "controller_check": "passed",
            "external_producers": "asserted_paused",
        }

    def quiesce(self, snapshot):
        require(
            set(snapshot) == set(self.config["workloads"]),
            "Workload recovery snapshot incomplete",
        )
        current = self.workload_snapshot()
        require(
            all(current[k]["uid"] == snapshot[k]["uid"] for k in snapshot),
            "Workload replaced during reset",
        )
        for resource in snapshot:
            command(
                self.store.prefix
                + [
                    "scale",
                    resource,
                    "--replicas=0",
                    "--current-replicas=" + str(current[resource]["replicas"]),
                ]
            )
        self.assert_drained()

    def assert_drained(self):
        for resource in self.config["workloads"]:
            obj = json.loads(
                command(self.store.prefix + ["get", resource, "-o", "json"])
            )
            require(
                obj["spec"].get("replicas", 1) == 0
                and obj.get("status", {}).get("replicas", 0) == 0,
                "Target workloads have not drained; retry without resetting",
            )
        active = self.sql(
            "SELECT count(*) FROM pg_stat_activity WHERE datname=%s",
            (self.target["database"],),
        )[0][0]
        require(active == 0, "Target database still has clients; no forced termination")

    def reset(self):
        self.store.check_cluster()
        self.check_database()
        self.assert_drained()
        # DROP without FORCE cannot kill another workload or hide incomplete drain.
        self.sql("DROP DATABASE " + identifier(self.target["database"]))
        self.create()

    def create(self):
        require(
            not self.check_database(absent_ok=True),
            "Creation requires absent target; never repeat DROP",
        )
        self.sql(
            "CREATE DATABASE "
            + identifier(self.target["database"])
            + " OWNER "
            + identifier(self.target["owner"])
        )

    def run_native(self, stage):
        # Reviewed scripts/jobs must use pinned native images, read their mounted
        # Secrets, and limit changes to this target. Their output stays private.
        env = {
            **os.environ,
            "RESET_TARGET_JSON": json.dumps(self.target),
            "RESET_EPOCH": self.config["epoch"],
            "RESET_PROTECTED_DIRECTORY": str(self.directory),
        }
        command(self.config["commands"][stage], env=env)

    def resume_workloads(self, snapshot, *, only=None):
        current = self.workload_snapshot()
        require(
            set(current) == set(snapshot)
            and all(current[k]["uid"] == snapshot[k]["uid"] for k in current),
            "Workload identity changed",
        )
        for resource, item in snapshot.items():
            if only is not None and resource not in only:
                continue
            command(
                self.store.prefix
                + ["scale", resource, "--replicas=" + str(item["replicas"])]
            )


def rebuild(config, store, actions, *, resume=False, initialize=False):
    """Execute one reviewed epoch. Missing receipts require explicit initialization.

    On RESET_STARTED recovery, an absent DB may only be created. An existing DB
    is ambiguous (old DB or created DB before receipt CAS), so manual recovery is
    required. This avoids a second DROP even across process/receipt failures.
    """
    validate(config)
    require(config.get("enabled") is True, "Reset is disabled")
    store.check_cluster()
    version, receipt = store.read()
    key = fingerprint(config)
    if receipt is None:
        require(
            initialize and not resume,
            "Missing receipt requires reviewed initialization, never implicit resume",
        )
        actions.check_database()
        receipt = {
            "fingerprint": key,
            "target": config["target"],
            "epoch": config["epoch"],
            "state": "PLANNED",
            "lock": None,
        }
        version = store.cas(None, receipt)
    require(
        receipt.get("fingerprint") == key
        and receipt.get("target") == config["target"]
        and receipt.get("epoch") == config["epoch"]
        and receipt.get("state") in STATES,
        "Receipt identity/state mismatch",
    )
    if receipt["state"] == "VERIFIED":
        return "SKIPPED_VERIFIED"
    require(
        not receipt.get("lock"),
        "Reset already owned; confirm prior process stopped before reviewed lock recovery",
    )
    require(
        resume or receipt["state"] == "PLANNED",
        "Incomplete epoch requires explicit resume",
    )
    owner = uuid.uuid4().hex
    receipt = {**receipt, "lock": owner}
    version = store.cas(version, receipt)

    def save(state, **extra):
        nonlocal receipt, version
        receipt = {**receipt, **extra, "state": state}
        version = store.cas(version, receipt)

    try:
        # Idempotent reviewed commands pause/assert delivery owned outside the
        # registry release. They preserve queue contents and checkpoints.
        actions.run_native("pause_producers")
        evidence = actions.preflight()
        save(receipt["state"], quiescence=evidence)
        if receipt["state"] == "PLANNED":
            actions.check_database()
            # Persist replicas before scaling, then freeze writes before taking
            # the recovery archive. A backup taken while producers still run
            # would omit writes accepted between pg_dump and quiescence.
            if not receipt.get("workloads"):
                save("PLANNED", workloads=actions.workload_snapshot())
            actions.quiesce(receipt["workloads"])
            save(
                "BACKED_UP",
                backup=actions.backup(),
            )
        actions.verify_backup(receipt.get("backup", {}))
        require(receipt.get("workloads"), "Receipt lacks target workload snapshot")
        if receipt["state"] == "BACKED_UP":
            actions.quiesce(receipt["workloads"])
            save("QUIESCED")
        if receipt["state"] == "QUIESCED":
            actions.preflight()
            actions.check_database()
            actions.assert_drained()
            save("RESET_STARTED")
            actions.reset()
            save("DB_CREATED")
        elif receipt["state"] == "RESET_STARTED":
            actions.assert_drained()
            require(
                not actions.check_database(absent_ok=True),
                "Ambiguous RESET_STARTED with existing database: manual recovery required, DROP will not repeat",
            )
            actions.create()
            save("DB_CREATED")
        if receipt["state"] == "DB_CREATED":
            actions.check_database()
            actions.run_native("migrate")
            actions.run_native("seed")
            save("SEEDED")
        if receipt["state"] == "SEEDED":
            actions.resume_workloads(
                receipt["workloads"], only=config["verification_workloads"]
            )
            actions.run_native("verify")
            save("ACCEPTED")
        if receipt["state"] == "ACCEPTED":
            # This separate durable state can resume interrupted restoration
            # without repeating migration, verification or the destructive step.
            actions.resume_workloads(receipt["workloads"])
            actions.run_native("resume_producers")
            save("VERIFIED")
        return "VERIFIED"
    except Exception:
        # Failures after destructive intent leave only the exact target paused.
        if STATES.index(receipt["state"]) >= STATES.index("RESET_STARTED"):
            actions.run_native("pause_producers")
            actions.quiesce(receipt["workloads"])
        raise
    finally:
        # Never overwrite another writer or a lost-CAS state with a stale receipt.
        current_version, current = store.read()
        if current_version == version and current.get("lock") == owner:
            store.cas(version, {**current, "lock": None})


def require_verified(config, store):
    """Read-only ordinary-deployment gate; never constructs DB/actions adapters."""
    validate(config)
    store.check_cluster()
    version, receipt = store.read()
    require(
        version is not None and isinstance(receipt, dict),
        "Verified reset receipt is missing",
    )
    require(
        receipt.get("target") == config["target"]
        and receipt.get("epoch") == config["epoch"]
        and receipt.get("fingerprint") == fingerprint(config),
        "Verified reset receipt does not match immutable manifest",
    )
    require(
        receipt.get("state") == "VERIFIED" and receipt.get("lock") is None,
        "Reset receipt is incomplete or locked",
    )
    require("lock" in receipt, "Reset receipt lock state is missing")
    return "VERIFIED_READ_ONLY"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--require-verified", action="store_true")
    parser.add_argument("--initialize-receipt", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--admin-service", help="Mounted libpq service name; never a DSN"
    )
    args = parser.parse_args()
    try:
        config = json.loads(args.manifest.read_text())
        validate(config)
        if args.require_verified:
            require(
                not args.initialize_receipt
                and not args.resume
                and not args.admin_service,
                "Read-only verification cannot initialize, resume or accept database administration",
            )
            print(require_verified(config, ConfigMapStore(config)))
            return
        if not args.execute:
            print("PLAN_ONLY " + fingerprint(config))
            return
        require(
            args.admin_service and re.fullmatch(r"[a-zA-Z0-9_-]+", args.admin_service),
            "Mounted libpq admin service required",
        )
        store = ConfigMapStore(config)
        print(
            rebuild(
                config,
                store,
                Actions(config, store, args.admin_service),
                resume=args.resume,
                initialize=args.initialize_receipt,
            )
        )
    except Exception as error:  # noqa: BLE001 -- CLI boundary must redact driver errors
        # DB/command exceptions may contain credentials; never print their text.
        print(
            "RESET_REFUSED: "
            + (
                str(error)
                if isinstance(error, Refused)
                else "protected operation failed; inspect receipt and private diagnostics"
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
