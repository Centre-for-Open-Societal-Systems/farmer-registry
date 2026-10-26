"""Reset failure/recovery boundaries; no cluster access or environment data."""

import copy
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).parents[2] / "ci/deploy/reset_new_dev.py"
SPEC = importlib.util.spec_from_file_location("reset_new_dev", PATH)
reset = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reset)


def config():
    target = {
        "registry": "farmer",
        "namespace": "farmer",
        "context": "new-dev-test",
        "cluster_uid": "owned-cluster",
        "release": "farmer-registry",
        "database": "farmer_registry",
        "owner": "farmer_owner",
        "database_server_address": "192.0.2.10",
        "database_server_port": 5432,
    }
    return {
        "version": 1,
        "environment": "new-dev",
        "enabled": True,
        "target": target,
        "allowlist": [copy.deepcopy(target)],
        "epoch": "native-1-2",
        "source_commit": "a" * 40,
        "chart": "registry:dev.12",
        "images": {str(i): "registry/image@sha256:" + "b" * 64 for i in range(5)},
        "workloads": ["deployment/farmer-api", "deployment/farmer-worker"],
        "verification_workloads": ["deployment/farmer-api"],
        "protected_directory": str(Path(__file__).resolve().parent / "private-reset"),
        "commands": {
            stage: ["python3", "reviewed_" + stage + ".py"]
            for stage in (
                "snapshot",
                "migrate",
                "seed",
                "verify",
                "pause_producers",
                "assert_producers_paused",
                "resume_producers",
            )
        },
    }


class Store:
    def __init__(self):
        self.version, self.receipt = None, None
        self.conflict = False

    def check_cluster(self):
        pass

    def read(self):
        return self.version, copy.deepcopy(self.receipt)

    def cas(self, version, receipt):
        if self.conflict or version != self.version:
            raise reset.Refused("CAS conflict")
        self.version = (self.version or 0) + 1
        self.receipt = copy.deepcopy(receipt)
        return self.version


class Actions:
    def __init__(self):
        self.exists, self.drops, self.creates = True, 0, 0
        self.events, self.fail = [], None

    def event(self, name):
        self.events.append(name)
        if self.fail == name:
            raise reset.Refused("Owned failure")

    def check_database(self, absent_ok=False):
        reset.require(absent_ok or self.exists, "Missing database")
        return self.exists

    def backup(self):
        self.event("backup")
        return {"restore_verified": True, "sha256": "owned"}

    def workload_snapshot(self):
        return {
            "deployment/farmer-api": {"uid": "owned", "replicas": 1},
            "deployment/farmer-worker": {"uid": "worker", "replicas": 1},
        }

    def preflight(self):
        self.event("preflight")
        return {"controller_check": "passed"}

    def verify_backup(self, backup):
        reset.require(backup.get("restore_verified") is True, "Backup absent")
        self.event("verify_backup")

    def quiesce(self, snapshot):
        self.event("quiesce")

    def assert_drained(self):
        self.event("drain")

    def reset(self):
        self.drops += 1
        self.exists = False
        self.event("after_drop")
        self.create()

    def create(self):
        reset.require(not self.exists, "DB exists")
        self.creates += 1
        self.exists = True
        self.event("after_create")

    def run_native(self, stage):
        self.event(stage)

    def resume_workloads(self, snapshot, *, only=None):
        self.event("resume_verification" if only is not None else "resume_workloads")


def test_success_and_completed_receipt_skip():
    c, s, a = config(), Store(), Actions()
    assert reset.rebuild(c, s, a, initialize=True) == "VERIFIED"
    assert a.drops == a.creates == 1
    assert s.receipt["lock"] is None
    assert a.events.index("resume_verification") < a.events.index("verify")
    assert a.events.index("verify") < a.events.index("resume_workloads")
    assert a.events.index("resume_workloads") < a.events.index("resume_producers")
    before = list(a.events)
    assert reset.rebuild(c, s, a) == "SKIPPED_VERIFIED"
    assert a.events == before


@pytest.mark.parametrize(
    "field,value", [("environment", "staging"), ("enabled", False), ("allowlist", [])]
)
def test_unsafe_manifest_never_drops(field, value):
    c, s, a = config(), Store(), Actions()
    c[field] = value
    with pytest.raises(reset.Refused):
        reset.rebuild(c, s, a, initialize=True)
    assert a.drops == 0


@pytest.mark.parametrize(
    "database",
    [
        "postgres",
        "commons_registry",
        "farmer;DROP DATABASE x",
        'farmer"',
        "template0",
        "awe_registry",
    ],
)
def test_system_and_injected_targets_refused(database):
    c = config()
    c["target"]["database"] = c["allowlist"][0]["database"] = database
    with pytest.raises(reset.Refused):
        reset.validate(c)


def test_missing_receipt_never_implicitly_initializes():
    a = Actions()
    with pytest.raises(reset.Refused):
        reset.rebuild(config(), Store(), a, resume=True)
    assert a.drops == 0


def test_lock_and_cas_conflict_prevent_all_actions():
    c, s, a = config(), Store(), Actions()
    s.conflict = True
    with pytest.raises(reset.Refused):
        reset.rebuild(c, s, a, initialize=True)
    assert not a.events


@pytest.mark.parametrize(
    "failure,state",
    [
        ("backup", "PLANNED"),
        ("quiesce", "PLANNED"),
        ("drain", "QUIESCED"),
        ("after_drop", "RESET_STARTED"),
        ("after_create", "RESET_STARTED"),
        ("migrate", "DB_CREATED"),
        ("seed", "DB_CREATED"),
        ("verify", "SEEDED"),
        ("resume_verification", "SEEDED"),
        ("resume_workloads", "ACCEPTED"),
        ("resume_producers", "ACCEPTED"),
    ],
)
def test_interrupted_states_do_not_repeat_drop(failure, state):
    c, s, a = config(), Store(), Actions()
    a.fail = failure
    with pytest.raises(reset.Refused):
        reset.rebuild(c, s, a, initialize=True)
    assert s.receipt["state"] == state
    assert s.receipt["lock"] is None
    drops = a.drops
    a.fail = None
    if state == "RESET_STARTED" and a.exists:
        with pytest.raises(reset.Refused, match="Ambiguous"):
            reset.rebuild(c, s, a, resume=True)
    else:
        assert reset.rebuild(c, s, a, resume=True) == "VERIFIED"
    assert a.drops <= max(1, drops)


def test_foreign_lock_and_manifest_drift_refused():
    c, s, a = config(), Store(), Actions()
    a.fail = "backup"
    with pytest.raises(reset.Refused):
        reset.rebuild(c, s, a, initialize=True)
    s.receipt["lock"] = "other-run"
    with pytest.raises(reset.Refused, match="already owned"):
        reset.rebuild(c, s, a, resume=True)
    s.receipt["lock"] = None
    c["source_commit"] = "c" * 40
    with pytest.raises(reset.Refused, match="identity"):
        reset.rebuild(c, s, a, resume=True)


def test_configmap_cas_uses_resource_version(monkeypatch):
    calls = []

    def fake(argv, **kwargs):
        import json

        calls.append((argv, json.loads(kwargs["stdin"])))
        return '{"metadata":{"resourceVersion":"8"}}'

    monkeypatch.setattr(reset, "command", fake)
    store = reset.ConfigMapStore(config())
    assert store.cas("7", {"state": "PLANNED"}) == "8"
    assert "replace" in calls[0][0]
    assert calls[0][1]["metadata"]["resourceVersion"] == "7"


def test_backup_failure_prevents_drop_and_archive_follows_quiescence():
    c, s, a = config(), Store(), Actions()
    a.fail = "verify_backup"
    with pytest.raises(reset.Refused):
        reset.rebuild(c, s, a, initialize=True)
    assert a.events.index("quiesce") < a.events.index("backup")
    assert a.drops == 0


def test_receipt_name_does_not_change_with_epoch():
    c = config()
    first = reset.ConfigMapStore(c).name
    c["epoch"] = "second-attempt"
    assert reset.ConfigMapStore(c).name == first


def test_wrong_database_server_refused_before_target_query(monkeypatch):
    c = config()
    actions = reset.Actions(c, Store(), "mounted-service")
    calls = []

    def sql(query, values=None):
        calls.append(query)
        return [("192.0.2.99", 5432)]

    monkeypatch.setattr(actions, "sql", sql)
    with pytest.raises(reset.Refused, match="server identity"):
        actions.check_database()
    assert len(calls) == 1


def test_tampered_backup_never_passes_verification(tmp_path):
    c = config()
    c["protected_directory"] = str(tmp_path)
    tmp_path.chmod(0o700)
    archive = tmp_path / (c["epoch"] + ".dump")
    snapshot = tmp_path / (c["epoch"] + ".snapshot.json")
    archive.write_bytes(b"owned archive")
    snapshot.write_text("{}")
    archive.chmod(0o600)
    snapshot.chmod(0o600)
    a = reset.Actions(c, Store(), "mounted-service")
    # Windows chmod cannot express owner-only POSIX permissions; the real
    # permission enforcement runs on the Linux CI host, not this pure fixture.
    if __import__("os").name == "nt":
        pytest.skip("POSIX protected-artifact test")
    evidence = {
        "restore_verified": True,
        "sha256": reset.digest(archive),
        "bytes": archive.stat().st_size,
        "snapshot_sha256": reset.digest(snapshot),
    }
    a.verify_backup(evidence)
    archive.write_bytes(b"changed")
    with pytest.raises(reset.Refused, match="mismatch"):
        a.verify_backup(evidence)


@pytest.mark.parametrize(
    "kind,obj",
    [
        (
            "horizontalpodautoscalers",
            {"metadata": {"labels": {"app.kubernetes.io/instance": "farmer-registry"}}},
        ),
        (
            "horizontalpodautoscalers",
            {"metadata": {}, "spec": {"scaleTargetRef": {"name": "farmer-api"}}},
        ),
        (
            "cronjobs",
            {
                "metadata": {
                    "labels": {"app.kubernetes.io/instance": "farmer-registry"}
                },
                "spec": {"suspend": False},
            },
        ),
        (
            "jobs",
            {
                "metadata": {
                    "labels": {"app.kubernetes.io/instance": "farmer-registry"}
                },
                "status": {"active": 1},
            },
        ),
    ],
)
def test_controller_preflight_refuses_target_writers(monkeypatch, kind, obj):
    import json

    store = reset.ConfigMapStore(config())
    monkeypatch.setattr(store, "check_cluster", lambda: None)
    a = reset.Actions(config(), store, "mounted-service")
    monkeypatch.setattr(a, "workload_snapshot", dict)
    monkeypatch.setattr(a, "run_native", lambda stage: None)
    monkeypatch.setattr(
        reset,
        "command",
        lambda argv, **kwargs: json.dumps({"items": [obj] if kind in argv else []}),
    )
    with pytest.raises(reset.Refused):
        a.preflight()


def test_controller_preflight_accepts_suspended_target_and_ignores_other_release(
    monkeypatch,
):
    import json

    store = reset.ConfigMapStore(config())
    monkeypatch.setattr(store, "check_cluster", lambda: None)
    a = reset.Actions(config(), store, "mounted-service")
    monkeypatch.setattr(a, "workload_snapshot", dict)
    stages = []
    monkeypatch.setattr(a, "run_native", stages.append)

    def output(argv, **kwargs):
        if "cronjobs" in argv:
            items = [
                {
                    "metadata": {
                        "labels": {"app.kubernetes.io/instance": "farmer-registry"}
                    },
                    "spec": {"suspend": True},
                }
            ]
        else:
            items = [
                {
                    "metadata": {"labels": {"app.kubernetes.io/instance": "commons"}},
                    "status": {"active": 1},
                }
            ]
        return json.dumps({"items": items})

    monkeypatch.setattr(reset, "command", output)
    assert a.preflight()["external_producers"] == "asserted_paused"
    assert stages == ["assert_producers_paused"]


def test_external_pause_failure_prevents_backup_and_drop():
    a = Actions()
    a.fail = "pause_producers"
    with pytest.raises(reset.Refused):
        reset.rebuild(config(), Store(), a, initialize=True)
    assert "backup" not in a.events and a.drops == 0


@pytest.mark.parametrize(
    "controlled",
    [[], ["deployment/foreign"], ["deployment/farmer-api", "deployment/farmer-worker"]],
)
def test_verification_subset_must_exclude_producers(controlled):
    c = config()
    c["verification_workloads"] = controlled
    with pytest.raises(reset.Refused, match="proper subset"):
        reset.validate(c)


def test_interrupted_restore_resumes_without_reverification_or_second_drop():
    c, s, a = config(), Store(), Actions()
    a.fail = "resume_producers"
    with pytest.raises(reset.Refused):
        reset.rebuild(c, s, a, initialize=True)
    assert s.receipt["state"] == "ACCEPTED"
    assert a.events[-1] == "quiesce"
    a.fail = None
    before = len(a.events)
    reset.rebuild(c, s, a, resume=True)
    assert "verify" not in a.events[before:]
    assert a.drops == 1


def verified_store(c):
    s = Store()
    s.version = 1
    s.receipt = {
        "target": copy.deepcopy(c["target"]),
        "epoch": c["epoch"],
        "fingerprint": reset.fingerprint(c),
        "state": "VERIFIED",
        "lock": None,
    }
    return s


def test_require_verified_is_read_only(monkeypatch):
    c = config()
    s = verified_store(c)
    monkeypatch.setattr(s, "cas", lambda *args: pytest.fail("Receipt mutation"))
    assert reset.require_verified(c, s) == "VERIFIED_READ_ONLY"


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "SEEDED"),
        ("state", "ACCEPTED"),
        ("lock", "running"),
        ("fingerprint", "other"),
        ("epoch", "other"),
        ("target", {}),
    ],
)
def test_require_verified_refuses_drift_incomplete_or_locked(field, value):
    c = config()
    s = verified_store(c)
    s.receipt[field] = value
    with pytest.raises(reset.Refused):
        reset.require_verified(c, s)


def test_require_verified_missing_receipt_does_not_initialize(monkeypatch):
    s = Store()
    monkeypatch.setattr(s, "cas", lambda *args: pytest.fail("Receipt initialized"))
    with pytest.raises(reset.Refused, match="missing"):
        reset.require_verified(config(), s)


def test_cli_guard_does_not_construct_actions_or_require_admin(
    tmp_path, monkeypatch, capsys
):
    import json
    import sys

    c = config()
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(c))
    s = verified_store(c)
    monkeypatch.setattr(reset, "ConfigMapStore", lambda value: s)
    monkeypatch.setattr(
        reset, "Actions", lambda *args: pytest.fail("Actions instantiated")
    )
    monkeypatch.setattr(s, "cas", lambda *args: pytest.fail("Mutation"))
    monkeypatch.setattr(
        sys, "argv", ["reset_new_dev.py", str(path), "--require-verified"]
    )
    reset.main()
    assert "VERIFIED_READ_ONLY" in capsys.readouterr().out


@pytest.mark.parametrize("extra", ["--initialize-receipt", "--resume", "--execute"])
def test_cli_guard_refuses_mutating_flags(tmp_path, monkeypatch, extra):
    import json
    import sys

    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(config()))
    monkeypatch.setattr(
        reset, "Actions", lambda *args: pytest.fail("Actions instantiated")
    )
    monkeypatch.setattr(
        sys, "argv", ["reset_new_dev.py", str(path), "--require-verified", extra]
    )
    with pytest.raises(SystemExit) as result:
        reset.main()
    assert result.value.code != 0


def test_guard_checks_actual_cluster_before_receipt(monkeypatch):
    s = verified_store(config())

    def refuse():
        raise reset.Refused("Wrong cluster")

    monkeypatch.setattr(s, "check_cluster", refuse)
    monkeypatch.setattr(
        s, "read", lambda: pytest.fail("Untrusted cluster receipt read")
    )
    with pytest.raises(reset.Refused, match="Wrong cluster"):
        reset.require_verified(config(), s)


@pytest.mark.parametrize("state", ["missing", "incomplete", "drift", "missing-lock"])
def test_cli_guard_failure_is_nonzero_without_mutation(tmp_path, monkeypatch, state):
    import json
    import sys

    c = config()
    s = verified_store(c)
    if state == "missing":
        s.version = s.receipt = None
    elif state == "incomplete":
        s.receipt["state"] = "PLANNED"
    elif state == "drift":
        s.receipt["fingerprint"] = "different"
    else:
        s.receipt.pop("lock")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(c))
    monkeypatch.setattr(reset, "ConfigMapStore", lambda value: s)
    monkeypatch.setattr(
        reset, "Actions", lambda *args: pytest.fail("Actions instantiated")
    )
    monkeypatch.setattr(s, "cas", lambda *args: pytest.fail("Mutation"))
    monkeypatch.setattr(
        sys, "argv", ["reset_new_dev.py", str(path), "--require-verified"]
    )
    with pytest.raises(SystemExit) as result:
        reset.main()
    assert result.value.code == 1
