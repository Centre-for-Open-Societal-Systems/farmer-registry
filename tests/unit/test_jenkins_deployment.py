"""Safety properties for upgrading the existing new-dev release."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("deployment", ROOT / "ci/deploy/deployment.py")
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)
ECR = "379220350808.dkr.ecr.ap-south-1.amazonaws.com"
TAG = "abcdef012345"


def helm_status(state="deployed", revision=5):
    return {"name": "farmer-registry", "namespace": "farmer", "version": revision,
            "info": {"status": state}}


@pytest.mark.parametrize("log,expected", [
    ('Error: post-upgrade hooks failed: job farmer-registry-db-seed failed: BackoffLimitExceeded', 'retries'),
    ('Error: timed out waiting for the condition', 'timed out'),
    ('Error: ImagePullBackOff password=private-value', 'pull its image'),
    ('Error: cannot patch deployment; private-value', 'resource update'),
    ('Error: unexpected private-value', 'unclassified'),
])
def test_helm_failure_diagnostics_do_not_echo_private_output(log, expected):
    result = ' '.join(deployment.upgrade_diagnostic(log))
    assert expected in result
    assert 'private-value' not in result


@pytest.mark.parametrize("state", ["deployed", "failed"])
def test_release_accepts_stable_upgrade_states(state):
    assert deployment.release_status(helm_status(state)) == state


@pytest.mark.parametrize("state", ["pending-install", "pending-upgrade", "pending-rollback",
                                  "uninstalling", "uninstalled", "superseded", "unknown", None])
def test_release_blocks_unstable_or_missing_state(state):
    with pytest.raises(ValueError, match="resolve Helm state"):
        deployment.release_status(helm_status(state))


@pytest.mark.parametrize("key,value", [("name", "other"), ("namespace", "commons"),
                                     ("version", 0), ("version", None), ("version", True)])
def test_release_identity_and_revision_required(key, value):
    status = helm_status()
    status[key] = value
    with pytest.raises(ValueError):
        deployment.release_status(status)


def test_failed_release_is_not_successful_completion():
    with pytest.raises(ValueError):
        deployment.release_status(helm_status("failed"), require_deployed=True)
    assert deployment.release_status(helm_status(), require_deployed=True) == "deployed"


@pytest.mark.parametrize("current", [helm_status("failed", 6), helm_status("deployed", 5),
                                   helm_status("pending-upgrade", 6)])
def test_release_changes_during_preflight_are_rejected(current):
    with pytest.raises(ValueError):
        deployment.unchanged_release(helm_status("failed"), current)


def test_unchanged_failed_release_can_proceed_to_upgrade():
    deployment.unchanged_release(helm_status("failed"), helm_status("failed"))


@pytest.mark.parametrize("state,mode", [("deployed", "normal"), ("failed", "recovery")])
def test_upgrade_mode_stdout_is_safe_for_shell_capture(tmp_path, monkeypatch, capsys, state, mode):
    status = tmp_path / "status.json"
    status.write_text(json.dumps(helm_status(state)), encoding="utf-8")
    monkeypatch.setattr(deployment.sys, "argv", ["deployment.py", "upgrade-mode", str(status)])
    deployment.main()
    assert capsys.readouterr().out == mode + "\n"


def workload(kind, suffix, image, env=None):
    return {"kind": kind, "metadata": {"name": "farmer-registry-" + suffix},
            "spec": {"selector": {"matchLabels": {"app": suffix}}, "template": {"spec": {
                "containers": [{"name": "app", "image": image, "env": env or []}]}}}}


@pytest.fixture
def release():
    before = [workload("Deployment", "staff-portal-api", "old/staff-api:previous", [
        {"name": "REGISTRY_STAFF_PORTAL_API_DB_HOSTNAME", "value": "commons-postgresql.commons.svc.cluster.local"},
        {"name": "REGISTRY_STAFF_PORTAL_API_DB_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "farmer-registry", "key": "farmer-registry-db-user"}}},
    ]), workload("Deployment", "celery-worker", "old/celery:previous", [
        {"name": "REGISTRY_CELERY_WORKERS_AWE_BASE_URL", "value": "http://commons-services-awe"},
        {"name": "REGISTRY_CELERY_WORKERS_AWE_CLIENT_SECRET", "valueFrom": {"secretKeyRef": {"name": "farmer-registry-staff-portal", "key": "client_secret"}}},
    ]), workload("Deployment", "dashboard-api", "independent/dashboard:existing"),
        {"kind": "VirtualService", "metadata": {"name": "farmer-registry-staff-portal-ui"},
         "spec": {"hosts": ["registry.farmer-dev.oanstaging.com"], "gateways": ["internal"]}}]
    after = copy.deepcopy(before)
    existing = {(d["kind"], d["metadata"]["name"]): d for d in after}
    for _, (kind, suffix, image) in deployment.COMPONENTS.items():
        key = (kind, "farmer-registry-" + suffix)
        if key not in existing:
            existing[key] = workload(kind, suffix, "")
            after.append(existing[key])
        deployment.pod(existing[key])["containers"][0]["image"] = f"{ECR}/openg2p/farmer-registry/{image}:{TAG}"
    for doc in after:
        suffix = doc["metadata"]["name"].removeprefix("farmer-registry-")
        env = deployment.pod(doc)["containers"][0]["env"] if deployment.pod(doc).get("containers") else []
        env.extend({"name": name, "value": value} for name, value in deployment.location_env(suffix).items())
        env.extend(deployment.env_entry(name, value) for name, value in deployment.master_data_env(suffix).items())
    return before, after


def test_safe_existing_release_upgrade(release):
    deployment.validate(*release, ECR, TAG)


def test_identity_migration_requires_explicit_allowlist_and_keeps_other_settings(release):
    before, after = release
    for doc in after:
        suffix = doc["metadata"]["name"].removeprefix("farmer-registry-")
        env = deployment.pod(doc)["containers"][0]["env"] if deployment.pod(doc).get("containers") else []
        for name, value in deployment.identity_env(suffix).items():
            env[:] = [e for e in env if e["name"] != name]
            env.append(deployment.env_entry(name, value))
    deployment.validate(before, after, ECR, TAG, migrate_identity=True)
    # Secret references remain subject to the original preservation rules.
    deployment.pod(after[0])["containers"][0]["env"][1]["valueFrom"]["secretKeyRef"]["name"] = "wrong"
    with pytest.raises(ValueError, match="Secret reference"):
        deployment.validate(before, after, ECR, TAG, migrate_identity=True)


def test_identity_migration_missing_worker_configuration_is_rejected(release):
    with pytest.raises(ValueError, match="Identity migration was not rendered"):
        deployment.validate(*release, ECR, TAG, migrate_identity=True)


def test_identity_values_are_applied_only_when_requested(release):
    values = {"global": {"registryHostname": "registry.farmer-dev.oanstaging.com"}}
    default = deployment.prepare(values, release[0], ECR, TAG)
    assert "keycloakBaseUrl" not in default["global"]
    result = deployment.prepare(values, release[0], ECR, TAG, migrate_identity=True)
    assert result["global"]["keycloakRealm"] == "staff"
    assert result["global"]["keycloakBaseUrl"] == "https://keycloak-development.oanstaging.com"
    assert result["registry"]["staffUi"]["envVars"]["IAM_URL"] == "https://staff-iam-development.oanstaging.com"


def test_registry_provenance_rejects_wrong_or_missing_image_digest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "service-outcomes/registry-images.tsv"
    path.parent.mkdir()
    commit = TAG + "a" * 28
    names = {c[2] for c in deployment.COMPONENTS.values()}
    lines = [f"{name}\t{ECR}/openg2p/farmer-registry/{name}:{TAG}\tsha256:{'b' * 64}" for name in sorted(names)]
    path.write_text("\n".join(lines))
    assert set(deployment.registry_provenance(ECR, TAG, commit)) == names
    path.write_text("\n".join(lines[:-1]))
    with pytest.raises(ValueError, match="Missing"):
        deployment.registry_provenance(ECR, TAG, commit)


def test_prepare_retains_values_and_worker_awe_secrets(release):
    values = {"global": {"registryHostname": "registry.farmer-dev.oanstaging.com"},
              "dashboardApi": {"image": {"tag": "existing"}},
              "registry": {"staffUi": {"envVars": {"COOKIE_DOMAIN": ".oanstaging.com"}}}}
    result = deployment.prepare(values, release[0], ECR, TAG)
    assert "celeryWorker" not in values["registry"], "Must not mutate source values"
    worker = result["registry"]["celeryWorker"]
    assert worker["envVars"]["REGISTRY_CELERY_WORKERS_AWE_BASE_URL"] == "http://commons-services-awe"
    assert worker["envVarsFrom"]["REGISTRY_CELERY_WORKERS_AWE_CLIENT_SECRET"]["secretKeyRef"]["key"] == "client_secret"
    assert result["dashboardApi"] == values["dashboardApi"]
    assert result["registry"]["staffUi"]["envVars"]["COOKIE_DOMAIN"] == ".oanstaging.com"
    assert result["registry"]["dbSeed"]["loadSampleData"] is False
    assert result["registry"]["sanity"]["runE2e"] is False
    assert result["analytics"]["reportingViews"]["generate"] is False


@pytest.mark.parametrize("hostname", sorted(deployment.NEW_DEV_HOSTNAMES))
def test_new_dev_hostnames_are_accepted(release, hostname):
    values = {"global": {"registryHostname": hostname}}
    assert deployment.prepare(values, release[0], ECR, TAG)["global"]["registryHostname"] == hostname


def test_wrong_environment_is_rejected(release):
    with pytest.raises(ValueError, match="new-dev"):
        deployment.prepare({"global": {"registryHostname": "registry.production.example"}}, release[0], ECR, TAG)


def test_dashboard_removal_is_rejected(release):
    before, after = release
    after[:] = [d for d in after if d["metadata"]["name"] != "farmer-registry-dashboard-api"]
    with pytest.raises(ValueError, match="remove"):
        deployment.validate(before, after, ECR, TAG)


@pytest.mark.parametrize("variable", ["REGISTRY_STAFF_PORTAL_API_DB_HOSTNAME", "REGISTRY_STAFF_PORTAL_API_DB_PASSWORD"])
def test_db_or_secret_change_is_rejected(release, variable):
    before, after = release
    env = deployment.pod(after[0])["containers"][0]["env"]
    next(e for e in env if e["name"] == variable)["value"] = "unexpected"
    with pytest.raises(ValueError, match="environment/Secret"):
        deployment.validate(before, after, ECR, TAG)


def test_worker_awe_omission_is_rejected(release):
    before, after = release
    deployment.pod(after[1])["containers"][0]["env"] = []
    with pytest.raises(ValueError, match="AWE"):
        deployment.validate(before, after, ECR, TAG)


def test_browser_route_change_is_rejected(release):
    before, after = release
    after[3]["spec"]["hosts"] = ["placeholder.openg2p.org"]
    with pytest.raises(ValueError, match="ingress"):
        deployment.validate(before, after, ECR, TAG)


def test_connector_ownership_is_rejected(release):
    before, after = release
    after.append({"kind": "Service", "metadata": {"name": "farmer-connector-api"}, "spec": {}})
    with pytest.raises(ValueError, match="shared/connector"):
        deployment.validate(before, after, ECR, TAG)


def test_wrong_image_commit_is_rejected(release):
    before, after = release
    deployment.pod(after[0])["containers"][0]["image"] = "old/staff-api:previous"
    with pytest.raises(ValueError, match="commit image"):
        deployment.validate(before, after, ECR, TAG)


def test_demo_seed_is_rejected(release):
    before, after = release
    seed = next(d for d in after if d["metadata"]["name"] == "farmer-registry-db-seed")
    deployment.pod(seed)["containers"][0]["env"].append({"name": "LOAD_SAMPLE_DATA", "value": "true"})
    with pytest.raises(ValueError, match="loader"):
        deployment.validate(before, after, ECR, TAG)


def test_dashboard_image_is_not_silently_upgraded(release):
    before, after = release
    deployment.pod(after[2])["containers"][0]["image"] = "dashboard:new"
    with pytest.raises(ValueError, match="Dashboard image"):
        deployment.validate(before, after, ECR, TAG)
