"""Optional service release failures must not mutate unrelated releases or data."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


coordinator = module("coordinator", "ci/services/coordinator.py")
cutover = module("connector_cutover", "scripts/operations/connector/connector_cutover.py")
identity = module("identity_check", "scripts/operations/identity/check.py")
ECR = "123456789012.dkr.ecr.ap-south-1.amazonaws.com"
SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64


@pytest.fixture
def component():
    return {"name": "example", "repository": "https://github.com/example/example.git",
            "release": "example", "namespace": "farmer", "dockerfile": "Dockerfile",
            "chart": "helm/example", "imageValues": "image"}


def record(component):
    return {"commit": SHA, "repository": ECR + "/" + component.get("imageRepository", "openg2p/" + component["name"]),
            "tag": SHA[:12], "digest": DIGEST, "chartHash": "c" * 64, "outcome": "built"}


def deployment(name, image="old:v1", replicas=1):
    return {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": name},
            "spec": {"replicas": replicas, "selector": {"matchLabels": {"app": name}},
                     "template": {"spec": {"containers": [{"name": "app", "image": image,
                         "env": [{"name": "PASSWORD", "valueFrom": {"secretKeyRef": {"name": "existing", "key": "password"}}}]}]}}}}


@pytest.mark.parametrize("code,error", [(2, coordinator.SkipService), (128, coordinator.ServiceError), (1, coordinator.ServiceError)])
def test_missing_branch_is_distinct_from_auth_network_failure(monkeypatch, tmp_path, component, code, error):
    monkeypatch.setattr(coordinator.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, code, "", "private credential"))
    with pytest.raises(error) as failure:
        coordinator.checkout(component, "dev", tmp_path / "source")
    assert "private" not in str(failure.value)
    assert not (tmp_path / "source").exists()


def test_checkout_pins_resolved_develop_commit(monkeypatch, tmp_path, component):
    calls = []
    def ls_remote(args, **kwargs):
        assert args[-1] == "refs/heads/develop"
        return subprocess.CompletedProcess(args, 0, SHA + "\trefs/heads/develop\n", "")
    monkeypatch.setattr(coordinator.subprocess, "run", ls_remote)
    def run(args):
        calls.append(args)
        return SHA if args[-1] == "HEAD" else ""
    assert coordinator.checkout(component, "dev", tmp_path / "source", run) == SHA
    assert any(args[-1] == SHA and "fetch" in args for args in calls)
    assert any("--detach" in args for args in calls)


def test_source_race_is_rejected(tmp_path, component):
    with pytest.raises(coordinator.ServiceError, match="revision-changed"):
        coordinator.checkout(component, "staging", tmp_path / "source", lambda a: "d" * 40, commit=SHA)


def test_missing_build_files_skip_without_side_effects(tmp_path, component):
    with pytest.raises(coordinator.SkipService, match="application-files"):
        coordinator.layout(component, tmp_path)


@pytest.mark.parametrize("path", ["../outside", "../../Dockerfile"])
def test_source_paths_cannot_escape_checkout(tmp_path, path):
    with pytest.raises(coordinator.ServiceError, match="outside-source"):
        coordinator.relative_file(tmp_path, path)


def test_branch_policy_and_real_config(component):
    assert coordinator.branch("dev", component) == "develop"
    assert coordinator.branch("staging", component) == "staging"
    upstream = coordinator.configuration()[0]
    assert upstream["repository"] == "https://github.com/OpenG2P/registry-connector.git"
    assert coordinator.branch("dev", upstream) == "develop"
    configured = coordinator.configuration()
    assert {item["name"] for item in configured} == {"registry-connector", "farmer-registry-dashboard", "farmer-registry-dashboard-api"}
    assert all(item["namespace"] == "farmer" for item in configured)


def test_dashboard_ui_uses_registry_chart_without_chart_in_application_source(tmp_path):
    component = next(item for item in coordinator.configuration() if item["name"] == "farmer-registry-dashboard")
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    _, chart = coordinator.layout(component, tmp_path)
    assert chart == ROOT / "helm/farmer-registry-dashboard"
    assert not (tmp_path / "helm").exists()


def test_failed_api_rollout_prevents_dependent_dashboard_rollout(tmp_path):
    components = [item for item in coordinator.configuration() if item["name"] != "registry-connector"]
    called = []

    def deploy(component, *_args):
        called.append(component["name"])
        raise coordinator.ServiceError("api-rollout-failed")

    previous = {item["name"]: {"outcome": "built"} for item in components}
    result = coordinator.coordinate(components, "deploy", "dev", ECR, previous, tmp_path, deploy_fn=deploy)
    assert called == ["farmer-registry-dashboard-api"]
    assert result["farmer-registry-dashboard"]["reason"] == "dashboard-api-not-deployed"


def test_configuration_rejects_other_registry_ownership(tmp_path, component):
    config = tmp_path / "components.yaml"
    config.write_text(yaml.safe_dump({"cossAddons": {"components": [dict(component, namespace="livestock")]}}))
    with pytest.raises(ValueError, match="farmer namespace"):
        coordinator.configuration(config)


@pytest.mark.parametrize("repository", ["untrusted/farmer-registry/dashboard-ui", "oan/../dashboard-ui", "oan/dashboard-ui:latest"])
def test_configuration_rejects_invalid_image_repositories(tmp_path, component, repository):
    config = tmp_path / "components.yaml"
    config.write_text(yaml.safe_dump({"cossAddons": {"components": [dict(component, imageRepository=repository)]}}))
    with pytest.raises(ValueError, match="Invalid image repository"):
        coordinator.configuration(config)


@pytest.mark.parametrize("field,value", [("release", "commons-services"), ("namespace", "commons"),
                                        ("imageValues", "registry.staffApi.image"),
                                        ("repository", "https://github.com/example/other.git")])
def test_embedded_api_cannot_adopt_other_owners_or_image_values(tmp_path, field, value):
    api = copy.deepcopy(coordinator.configuration()[-1])
    api[field] = value
    config = tmp_path / "values.yaml"
    config.write_text(yaml.safe_dump({"cossAddons": {"components": [api]}}))
    with pytest.raises(ValueError):
        coordinator.configuration(config)


def test_service_catalogue_is_owned_by_helm_and_hash_covers_repositories(tmp_path, monkeypatch):
    assert coordinator.MANIFEST == ROOT / "helm/openg2p-farmer-registry/values.yaml"
    assert not (ROOT / "ci/services/components.yaml").exists()
    values = yaml.safe_load(coordinator.MANIFEST.read_text())
    path = tmp_path / "values.yaml"
    path.write_text(yaml.safe_dump(values))
    monkeypatch.setattr(coordinator, "MANIFEST", path)
    original = coordinator.configuration_hash()
    values["dashboardApi"]["replicas"] = 4
    path.write_text(yaml.safe_dump(values))
    assert coordinator.configuration_hash() == original
    values["cossAddons"]["components"][0]["repository"] = "https://github.com/example/changed.git"
    path.write_text(yaml.safe_dump(values))
    assert coordinator.configuration_hash() != original


def test_jenkins_transfers_hidden_chart_files_bound_into_the_build_hash():
    for path, name in [("ci/pipelines/dev.groovy", "dev-deployment"), ("ci/pipelines/dev.groovy", "optional-deployment")]:
        line = next(line for line in (ROOT / path).read_text().splitlines() if "stash name: '" + name + "'" in line)
        assert "helm/**" in line and "useDefaultExcludes: false" in line
        assert "scripts/**" in line and "integrations/**" in line and "tests/runtime/**" in line


def test_staging_components_target_far_without_adopting_the_legacy_connector():
    dev = coordinator.configuration()
    staging = coordinator.configuration(environment="staging")
    assert all(c["namespace"] == "farmer" for c in dev)
    assert all(c["namespace"] == "far" for c in staging)
    assert [c["release"] for c in dev] == [c["release"] for c in staging]
    assert all(c["release"] != "farmer-connector" for c in staging)


@pytest.mark.parametrize("mutation", ["none", "worker", "secret", "route", "job", "remove", "database"])
def test_dashboard_api_guard_preserves_every_other_resource(mutation):
    api = deployment("farmer-registry-dashboard-api")
    worker = deployment("farmer-registry-celery-worker")
    secret = {"kind": "Secret", "metadata": {"name": "farmer-registry"}, "data": {"password": "fixture"}}
    route = {"kind": "VirtualService", "metadata": {"name": "farmer-registry"}, "spec": {"hosts": ["unchanged.example"]}}
    before = [api, worker, secret, route]
    after = copy.deepcopy(before)
    image = "api:new@" + DIGEST
    coordinator.pod(after[0])["containers"][0]["image"] = image
    if mutation == "worker":
        coordinator.pod(after[1])["containers"][0]["image"] = image
    elif mutation == "secret":
        after[2]["data"]["password"] = "changed"
    elif mutation == "route":
        after[3]["spec"]["hosts"] = ["changed.example"]
    elif mutation == "job":
        after.append({"kind": "Job", "metadata": {"name": "setup"}})
    elif mutation == "remove":
        after.pop()
    elif mutation == "database":
        coordinator.pod(after[0])["containers"][0]["env"][0]["valueFrom"]["secretKeyRef"]["name"] = "another-db"
    if mutation == "none":
        coordinator.guard_dashboard_api(before, after, image)
    else:
        with pytest.raises(coordinator.ServiceError):
            coordinator.guard_dashboard_api(before, after, image)


def test_embedded_api_deploy_uses_approved_chart_filters_jobs_and_keeps_registry_owner(tmp_path, monkeypatch):
    component = coordinator.configuration()[-1]
    provenance = coordinator.dashboard_chart_provenance()
    monkeypatch.setattr(coordinator, "dashboard_chart_provenance", lambda: provenance)
    monkeypatch.setattr(coordinator, "ROOT", tmp_path)
    source = tmp_path / "api-source"
    source.mkdir()
    (source / "Dockerfile").write_text("FROM example:pin\n")
    chart = tmp_path / component["chart"]
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text("apiVersion: v2\nname: farmer\nversion: 1.0.0\n")
    values = tmp_path / "helm/environments/dev/services/farmer-registry-dashboard-api.yaml"
    values.parent.mkdir(parents=True)
    values.write_text("_coordination:\n  namespace: farmer\n")
    built = record(component)
    built["chartHash"] = coordinator.chart_hash(chart)
    built["deploymentChart"] = provenance
    image = coordinator.artifact(component, built, ECR)
    before = [deployment("farmer-registry-dashboard-api"), deployment("farmer-registry-celery-worker")]
    after = copy.deepcopy(before)
    coordinator.pod(after[0])["containers"][0]["image"] = image
    state = {"upgraded": False, "calls": []}
    monkeypatch.setattr(coordinator, "checkout", lambda *a, **kw: SHA)
    def prepare(directory, values, previous, installed_chart):
        assert installed_chart == "openg2p-farmer-registry-1.0.0-dev.5"
        assert previous == before
        archive = directory / "approved.tgz"
        archive.write_bytes(b"verified fixture")
        renderer = directory / "renderer"
        renderer.write_text("import sys,yaml\nyaml.safe_dump_all([d for d in yaml.safe_load_all(sys.stdin) if d.get('kind')!='Job'],sys.stdout)\n")
        state["chart"] = archive
        return archive, renderer
    monkeypatch.setattr(coordinator, "prepare_dashboard_chart", prepare)
    def run(args):
        state["calls"].append(args)
        if args[:2] == ["helm", "list"]:
            return '[{"name":"farmer-registry","chart":"openg2p-farmer-registry-1.0.0-dev.5"}]'
        if args[:2] == ["helm", "status"]:
            return json.dumps({"name": "farmer-registry", "namespace": "farmer", "version": 13 if state["upgraded"] else 12,
                               "info": {"status": "deployed"}})
        if args[:3] == ["helm", "get", "manifest"]:
            return yaml.safe_dump_all(after if state["upgraded"] else before)
        if args[:3] == ["helm", "get", "values"]:
            return "dashboardApi:\n  enabled: true\n"
        if args[:2] in (["helm", "template"], ["helm", "upgrade"]):
            assert args[2] == "farmer-registry" and args[3] == str(state["chart"])
            assert "--no-hooks" in args and "--post-renderer" in args
            renderer = Path(args[args.index("--post-renderer") + 1])
            filtered = subprocess.run([sys.executable, str(renderer)], input=yaml.safe_dump_all(after + [{"kind": "Job"}]),
                                      text=True, capture_output=True, check=True)
            assert coordinator.docs(filtered.stdout) == after
            selected = yaml.safe_load(Path(args[args.index("-f") + 1]).read_text())
            assert selected["dashboardApi"]["enabled"] is True
            assert selected["dashboardApi"]["image"]["repository"] == ECR + "/openg2p/farmer-registry/dashboard-api"
            if args[1] == "upgrade":
                state["upgraded"] = True
            return yaml.safe_dump_all(after)
        if args[:3] in (["helm", "dependency", "build"], ["helm", "repo", "add"]):
            return ""
        pytest.fail("Unexpected command")
    assert coordinator.deploy(component, "dev", built, source, ECR, run) == 13
    assert not any("uninstall" in call or "delete" in call for call in state["calls"])
    assert not any(call[:3] in (["helm", "repo", "add"], ["helm", "dependency", "build"]) for call in state["calls"])


@pytest.mark.parametrize("field", ["sha256", "version", "rendererHash"])
def test_embedded_api_rejects_changed_approved_chart_before_any_tool_call(tmp_path, field):
    component = coordinator.configuration()[-1]
    built = record(component)
    built["deploymentChart"] = coordinator.dashboard_chart_provenance()
    built["deploymentChart"][field] = "tampered"
    with pytest.raises(coordinator.ServiceError, match="approved-chart-provenance-mismatch"):
        coordinator.deploy(component, "dev", built, tmp_path, ECR, lambda *_: pytest.fail("Unexpected tool call"))


def test_embedded_api_rejects_wrong_installed_chart_before_download(tmp_path, monkeypatch):
    monkeypatch.setattr(coordinator.urllib.request, "urlopen", lambda *_args, **_kwargs: pytest.fail("Unexpected download"))
    with pytest.raises(coordinator.ServiceError, match="installed-chart-mismatch"):
        coordinator.prepare_dashboard_chart(tmp_path, {}, [], "another-chart-1.0.0")


def test_embedded_api_rejects_corrupt_approved_archive(tmp_path, monkeypatch):
    import io
    monkeypatch.setattr(coordinator.urllib.request, "urlopen", lambda *_args, **_kwargs: io.BytesIO(b"invalid chart bytes"))
    with pytest.raises(coordinator.ServiceError, match="download-or-checksum-failed"):
        coordinator.prepare_dashboard_chart(tmp_path, {}, [], "openg2p-farmer-registry-1.0.0-dev.5")


def test_embedded_api_restores_selected_digest_after_registry_reconciliation(tmp_path, monkeypatch):
    import io
    import deployment
    import oan_chart
    selected = {"repository": ECR + "/openg2p/farmer-registry/dashboard-api", "tag": SHA[:12] + "@" + DIGEST}
    values = {"dashboardApi": {"image": dict(selected, digest="old-digest")}}
    monkeypatch.setattr(coordinator.urllib.request, "urlopen", lambda *_args, **_kwargs: io.BytesIO(b"fixture"))
    monkeypatch.setattr(oan_chart, "verify", lambda _path: oan_chart.profile())
    def reconcile(candidate, _before):
        candidate["dashboardApi"]["image"] = {"repository": "old", "digest": "old-digest"}
    monkeypatch.setattr(deployment, "reconcile_dev", reconcile)
    monkeypatch.setenv("OAN_CHART_ARCHIVE", "previous-archive")
    archive, renderer = coordinator.prepare_dashboard_chart(tmp_path, values, [], "openg2p-farmer-registry-1.0.0-dev.5")
    assert values["dashboardApi"]["image"] == dict(selected, digest=None)
    assert coordinator.os.environ["OAN_CHART_ARCHIVE"] == "previous-archive"
    assert archive.is_file() and renderer.is_file()


@pytest.mark.parametrize("field", [None, "commit", "digest", "chartHash", "environment", "valuesHash", "harnessHash",
                                 "noExternalNetwork", "hookJobs", "everyEnabledHook", "rerun", "failureRecovery", "isolatedDatabases"])
def test_dashboard_hook_evidence_binds_image_chart_configuration_and_executed_checks(field):
    component = next(c for c in coordinator.configuration() if c.get("chartSource") == "registry")
    built = record(component)
    overrides = {"iamSetup": {"grantUsers": []}}
    import hashlib
    built["hookRehearsal"] = {"commit": SHA, "digest": DIGEST, "chartHash": built["chartHash"], "environment": "dev",
        "valuesHash": hashlib.sha256(json.dumps(overrides, sort_keys=True).encode()).hexdigest(),
        "harnessHash": coordinator.chart_hash(ROOT / "scripts/operations/dashboard"),
        "noExternalNetwork": True, "isolatedDatabases": True, "everyEnabledHook": True, "rerun": True, "failureRecovery": True,
        "hookJobs": [component["name"]+suffix for suffix in ("-ecr-refresh-init", "-iam-setup", "-chart-smoke")],
        "fixtureMode": "loopback-http-sqlite-kubectl-transport-shim"}
    if field is None:
        coordinator.rehearsal(component, "dev", built, overrides)
    else:
        built["hookRehearsal"].pop(field)
        with pytest.raises(coordinator.ServiceError, match="rehearsal"):
            coordinator.rehearsal(component, "dev", built, overrides)


@pytest.mark.parametrize("failure", [coordinator.ServiceError("command-failed-docker"),
                                    coordinator.SkipService("missing-branch"), RuntimeError("private-secret")])
def test_optional_failure_continues_independent_components(tmp_path, component, failure, capsys):
    second = dict(component, name="other", release="other")
    calls = []
    def build(item, *args):
        calls.append(item["name"])
        if item["name"] == "example":
            raise failure
        return record(item)
    result = coordinator.coordinate([component, second], "build", "dev", ECR, {}, tmp_path, build_fn=build)
    assert calls == ["example", "other"]
    assert result["example"]["outcome"] in ("failed", "skipped")
    assert result["other"]["outcome"] == "built"
    assert "private-secret" not in capsys.readouterr().out


def test_missing_replacement_build_never_calls_deploy(tmp_path, component):
    result = coordinator.coordinate([component], "deploy", "dev", ECR, {}, tmp_path,
                                    deploy_fn=lambda *a: pytest.fail("No build must mean no mutation"))
    assert result["example"]["outcome"] == "skipped"


def test_staging_never_rebuilds_connector_or_promotes_untested_images(tmp_path, component):
    component["kind"] = "connector"
    result = coordinator.coordinate([component], "build", "staging", ECR, {}, tmp_path,
                                    build_fn=lambda *a: pytest.fail("Staging must not rebuild"))
    assert result["example"]["outcome"] == "skipped"
    result = coordinator.coordinate([component], "deploy", "staging", ECR, {"example": record(component)}, tmp_path,
                                    deploy_fn=lambda *a: pytest.fail("Only dev deployed digests may promote"))
    assert result["example"]["reason"] == "connector-not-promoted-from-dev"


def test_staging_promotes_connector_digest_but_builds_dashboard_staging_branch(tmp_path, component):
    connector = dict(component, name="connector", release="connector", kind="connector")
    previous = record(connector)
    previous.update(outcome="deployed", helmRevision=6, stagingChartHash="e" * 64, stagingBackupHash="f" * 64)
    calls = []
    def build(item, environment, *args):
        calls.append((item["name"], coordinator.branch(environment, item)))
        return record(item)
    result = coordinator.coordinate([connector, component], "build", "staging", ECR,
                                    {"connector": previous}, tmp_path, build_fn=build)
    assert calls == [("example", "staging")]
    assert result["connector"]["digest"] == previous["digest"]
    assert result["connector"]["devHelmRevision"] == 6
    assert result["connector"]["devChartHash"] == previous["chartHash"]
    assert result["connector"]["chartHash"] == "e" * 64
    assert result["connector"]["stagingBackupHash"] == "f" * 64


@pytest.mark.parametrize("field,value", [("commit", "develop"), ("digest", "latest"),
                                        ("tag", "other"), ("repository", "unrelated/repo"), ("chartHash", "")])
def test_promotion_rejects_tampered_artifact(component, field, value):
    item = record(component)
    item[field] = value
    with pytest.raises(coordinator.ServiceError):
        coordinator.artifact(component, item, ECR)


def test_promoted_image_contains_exact_digest(component):
    assert coordinator.artifact(component, record(component), ECR) == ECR + "/openg2p/example:" + SHA[:12] + "@" + DIGEST


def test_all_connector_images_are_pinned_and_ui_tampering_is_rejected():
    component = coordinator.configuration()[0]
    images = {role: {"repository": ECR + "/openg2p/registry-connector-" + role,
                     "tag": SHA[:12], "digest": DIGEST} for role in ("api", "ui")}
    item = dict(images["api"], commit=SHA, chartHash="c" * 64, images=images)
    assert set(coordinator.image_artifacts(component, item, ECR)) == {"api", "ui"}
    images["ui"]["repository"] = "unrelated/image"
    with pytest.raises(coordinator.ServiceError, match="invalid-component-image"):
        coordinator.image_artifacts(component, item, ECR)


def test_connector_bundle_requires_both_api_and_ui_digests():
    component = coordinator.configuration()[0]
    item = {"repository": ECR + "/openg2p/registry-connector-api", "commit": SHA,
            "tag": SHA[:12], "digest": DIGEST, "chartHash": "c" * 64,
            "images": {"api": {"digest": DIGEST}}}
    with pytest.raises(coordinator.ServiceError, match="missing-component-image"):
        coordinator.image_artifacts(component, item, ECR)


def test_overlay_change_requires_another_image_tag():
    component = coordinator.configuration()[0]
    item = {"repository": ECR + "/openg2p/registry-connector-api", "commit": SHA,
            "tag": SHA[:12], "digest": DIGEST, "chartHash": "c" * 64,
            "overlayHashes": {"api": "d" * 64}}
    with pytest.raises(coordinator.ServiceError, match="invalid-promotion-artifact"):
        coordinator.artifact(component, item, ECR)


def test_persistent_guard_requires_every_image_in_the_bundle():
    with pytest.raises(coordinator.ServiceError, match="not-rendered"):
        coordinator.guard([], [deployment("api", "api@" + DIGEST)], "farmer", ["api@" + DIGEST, "ui@" + DIGEST])


def test_guard_allows_only_intended_image_change():
    old = deployment("example")
    new = copy.deepcopy(old)
    new["spec"]["template"]["spec"]["containers"][0]["image"] = "new@" + DIGEST
    coordinator.guard([old], [new], "farmer", "new@" + DIGEST)


def test_optional_upgrade_cannot_rotate_secret_data():
    old = {"kind": "Secret", "metadata": {"name": "example-auth"}, "data": {"password": "old"}}
    new = dict(old, data={"password": "changed"})
    with pytest.raises(coordinator.ServiceError, match="config-changed"):
        coordinator.guard([old], [new, deployment("example", "new@" + DIGEST)], "farmer", "new@" + DIGEST)


@pytest.mark.parametrize("mutation", ["remove", "secret", "selector", "namespace", "storage", "unrelated-image"])
def test_guard_preserves_resources_routing_storage_credentials(mutation):
    old = deployment("example")
    new = copy.deepcopy(old)
    new["spec"]["template"]["spec"]["containers"][0]["image"] = "new@" + DIGEST
    after = [new]
    if mutation == "remove":
        after = []
    elif mutation == "secret":
        new["spec"]["template"]["spec"]["containers"][0]["env"] = []
    elif mutation == "selector":
        new["spec"]["selector"] = {}
    elif mutation == "namespace":
        new["metadata"]["namespace"] = "commons"
    elif mutation == "storage":
        new["spec"]["template"]["spec"]["volumes"] = []
    else:
        old_other = deployment("unrelated")
        new_other = deployment("unrelated", "changed:v2")
        after.append(new_other)
        with pytest.raises(coordinator.ServiceError):
            coordinator.guard([old, old_other], after, "farmer", "new@" + DIGEST)
        return
    with pytest.raises(coordinator.ServiceError):
        coordinator.guard([old], after, "farmer", "new@" + DIGEST)


@pytest.mark.parametrize("kind,spec", [("Deployment", {}), ("StatefulSet", {"replicas": 1}),
                                       ("CronJob", {}), ("Job", {}), ("DaemonSet", {})])
def test_connector_preparation_rejects_any_running_automatic_process(kind, spec):
    with pytest.raises(coordinator.ServiceError):
        coordinator.paused_connector([{"kind": kind, "spec": spec}])


def test_paused_connector_has_no_ingestion():
    coordinator.paused_connector([deployment("replacement", replicas=0),
                                  {"kind": "CronJob", "spec": {"suspend": True}}])


@pytest.fixture
def accepted():
    old = [deployment("farmer-connector-worker", replicas=0)]
    status = {"name": cutover.NEW, "namespace": "farmer", "version": 2, "info": {"status": "deployed"}}
    review = {key: True for key in cutover.ACCEPTANCE}
    review.update(environment="dev", backupHash="backup", helmRevision=2, digest=DIGEST)
    return old, copy.deepcopy(old), status, [deployment(cutover.NEW, "image@" + DIGEST)], review, "backup"


def test_retirement_requires_every_acceptance_check(accepted):
    cutover.retirement_guard(*accepted)
    for check in cutover.ACCEPTANCE:
        data = copy.deepcopy(accepted)
        data[4][check] = False
        with pytest.raises(coordinator.ServiceError, match="acceptance-incomplete"):
            cutover.retirement_guard(*data)


@pytest.mark.parametrize("resource", [
    {"kind": "PersistentVolumeClaim", "metadata": {"name": "farmer-connector-data"}},
    {"kind": "StatefulSet", "metadata": {"name": "farmer-connector-postgres"}},
    {"kind": "Service", "metadata": {"name": "commons-keycloak"}},
    {"kind": "Namespace", "metadata": {"name": "farmer-connector-ns"}},
])
def test_retirement_cannot_delete_database_or_shared_resources(accepted, resource):
    accepted[0].append(resource)
    with pytest.raises(coordinator.ServiceError):
        cutover.retirement_guard(*accepted)


def test_retirement_preserves_explicitly_retained_storage(accepted):
    accepted[0].append({"kind": "PersistentVolumeClaim", "metadata": {"name": "farmer-connector-data",
                         "annotations": {"helm.sh/resource-policy": "keep"}}})
    cutover.retirement_guard(*accepted)


def test_retirement_rejects_still_running_old_workers(accepted):
    accepted[1][0]["status"] = {"replicas": 1}
    with pytest.raises(coordinator.ServiceError, match="not-stopped"):
        cutover.retirement_guard(*accepted)


@pytest.mark.parametrize("field,value", [("helmRevision", 3), ("digest", "sha256:" + "d" * 64),
                                        ("backupHash", "different"), ("environment", "staging")])
def test_retirement_rejects_stale_or_wrong_environment_acceptance(accepted, field, value):
    accepted[4][field] = value
    with pytest.raises(coordinator.ServiceError):
        cutover.retirement_guard(*accepted)


def test_backup_tampering_is_rejected(tmp_path):
    names = ("values.yaml", "manifest.yaml", "hooks.yaml", "pipelines.json", "mappings.json", "checkpoints.json", "database.dump")
    hashes = {}
    for name in names:
        file = tmp_path / name
        file.write_text("original")
        hashes[name] = cutover.sha(file)
    (tmp_path / "backup.json").write_text(json.dumps({"release": cutover.OLD, "namespace": "farmer", "files": hashes}))
    cutover.verify_backup(tmp_path)
    (tmp_path / "checkpoints.json").write_text("changed")
    with pytest.raises(coordinator.ServiceError, match="integrity"):
        cutover.verify_backup(tmp_path)


@pytest.fixture
def identity_inputs():
    issuer = identity.ISSUER
    endpoints = {key: issuer + suffix for key, suffix in (
        ("authorization_endpoint", "/protocol/openid-connect/auth"),
        ("token_endpoint", "/protocol/openid-connect/token"), ("userinfo_endpoint", "/protocol/openid-connect/userinfo"))}
    provider = dict(endpoints, id=1, active=True, issuer=issuer,
                    server_metadata_url=issuer + "/.well-known/openid-configuration",
                    oauth_callback_url=identity.IAM + "/auth/callback")
    awe = {"awe": {"keycloak": {"issuer": issuer, "realm": "staff", "audience": "awe",
           "base_url": issuer.removesuffix("/realms/staff"), "jwks_url": "http://commons-keycloak:80/realms/staff/protocol/openid-connect/certs"}}}
    key = {"keys": [{"kty": "RSA", "kid": "one", "n": "public", "e": "AQAB"}]}
    review = {name: True for name in identity.CHECKS}
    review.update(environment="dev", issuer=issuer, aweAudience="awe")
    return provider, awe, dict(endpoints, issuer=issuer), key, copy.deepcopy(key), review


def test_identity_keeps_internal_jwks_and_audience(identity_inputs):
    before = copy.deepcopy(identity_inputs)
    evidence = identity.check(*identity_inputs)
    assert evidence["issuer"] == identity.ISSUER
    assert identity_inputs == before
    assert "jwks_url" not in json.dumps(evidence)


@pytest.mark.parametrize("change", ["issuer", "keys", "audience", "roles", "realm", "callback"])
def test_identity_refuses_mismatched_issuer_keys_or_unverified_prerequisites(identity_inputs, change):
    provider, awe, discovery, public, internal, review = identity_inputs
    if change == "issuer": provider["issuer"] = "https://keycloak.commons-dev.oanstaging.com/realms/staff"
    if change == "keys": internal["keys"][0]["n"] = "different-key-same-kid"
    if change == "audience": review["aweAudience"] = "wrong"
    if change == "roles": review["rolesVerified"] = False
    if change == "realm": awe["awe"]["keycloak"]["realm"] = "wrong"
    if change == "callback": provider["oauth_callback_url"] = "https://other/auth/callback"
    with pytest.raises(ValueError):
        identity.check(*identity_inputs)


def test_issuer_diagnostic_returns_no_other_claims():
    import base64
    payload = base64.urlsafe_b64encode(json.dumps({"iss": identity.ISSUER, "sub": "private-user"}).encode()).decode().rstrip("=")
    assert identity.token_issuer("header." + payload + ".signature") == identity.ISSUER


def test_build_records_pushed_digest_and_verifies_it_by_digest(tmp_path, monkeypatch, component):
    source = tmp_path / "source"
    chart = source / component["chart"]
    chart.mkdir(parents=True)
    (source / "Dockerfile").write_text("FROM example:pin\n")
    (chart / "Chart.yaml").write_text("apiVersion: v2\nname: example\nversion: 1.0.0\n")
    monkeypatch.setattr(coordinator, "checkout", lambda *a, **kw: SHA)
    calls = []
    def run(args):
        calls.append(args)
        if args[:2] == ["docker", "push"]:
            return "tag: digest: " + DIGEST + " size: 100"
        if args[:3] == ["aws", "ecr", "describe-images"]:
            assert "imageDigest=" + DIGEST in args
            return DIGEST + "\n"
        return ""
    result = coordinator.build(component, "dev", source, ECR, run)
    assert result["commit"] == SHA
    assert result["digest"] == DIGEST
    assert result["chartHash"] == coordinator.chart_hash(chart)
    assert calls[0][:2] == ["docker", "build"]


@pytest.fixture
def release_tools(tmp_path, monkeypatch, component):
    monkeypatch.setattr(coordinator, "ROOT", tmp_path)
    source = tmp_path / "source"
    chart = source / component["chart"]
    chart.mkdir(parents=True)
    (source / "Dockerfile").write_text("FROM example:pin\n")
    (chart / "Chart.yaml").write_text("apiVersion: v2\nname: example\nversion: 1.0.0\n")
    values = tmp_path / "helm/environments/dev/services/example.yaml"
    values.parent.mkdir(parents=True)
    values.write_text("_coordination:\n  namespace: farmer\n")
    item = record(component)
    item["chartHash"] = coordinator.chart_hash(chart)
    monkeypatch.setattr(coordinator, "checkout", lambda *a, **kw: SHA)
    image = coordinator.artifact(component, item, ECR)
    old, new = deployment("example"), deployment("example", image)
    state = {"upgraded": False, "race": False, "hooks": False, "calls": []}
    def run(args):
        state["calls"].append(args)
        if args[:2] == ["helm", "list"]:
            return '[{"name":"example"}]'
        if args[:2] == ["helm", "status"]:
            count = sum(a[:2] == ["helm", "status"] for a in state["calls"])
            return json.dumps({"name": "example", "namespace": "farmer",
                               "version": 6 if state["upgraded"] or state["race"] and count > 1 else 5,
                               "info": {"status": "deployed"}})
        if args[:3] == ["helm", "get", "manifest"]:
            return yaml.safe_dump(new if state["upgraded"] else old)
        if args[:3] == ["helm", "get", "values"]:
            return "{}"
        if args[:3] == ["helm", "get", "hooks"]:
            return ""
        if args[:2] == ["helm", "template"]:
            result = yaml.safe_dump(new)
            if state["hooks"]:
                result += '\n---\nkind: Job\nmetadata:\n  name: example-migrate\n  annotations:\n    helm.sh/hook: pre-upgrade\n'
            return result
        if args[:2] == ["helm", "upgrade"]:
            state["upgraded"] = True
            return ""
        if args[:3] == ["helm", "dependency", "build"]:
            return ""
        if args[:3] == ["helm", "repo", "add"]:
            return ""
        pytest.fail("Unexpected command " + repr(args))
    return source, item, state, run


def test_real_deploy_orchestration_pins_digest_preserves_values_and_records_revision(component, release_tools):
    source, item, state, run = release_tools
    assert coordinator.deploy(component, "dev", item, source, ECR, run) == 6
    upgrade = next(a for a in state["calls"] if a[:2] == ["helm", "upgrade"])
    assert "--atomic" in upgrade and "--wait-for-jobs" in upgrade
    assert not any("uninstall" in a or "delete" in a for a in state["calls"])


def test_deploy_stops_before_mutation_when_release_changes(component, release_tools):
    source, item, state, run = release_tools
    state["race"] = True
    with pytest.raises(coordinator.ServiceError, match="changed-during-preflight"):
        coordinator.deploy(component, "dev", item, source, ECR, run)
    assert not state["upgraded"]


def test_unrehearsed_hook_never_runs(component, release_tools):
    source, item, state, run = release_tools
    state["hooks"] = True
    with pytest.raises(coordinator.ServiceError, match="rehearsal-required"):
        coordinator.deploy(component, "dev", item, source, ECR, run)
    assert not state["upgraded"]


def test_missing_environment_config_preserves_release_without_helm_calls(component, release_tools, monkeypatch, tmp_path):
    source, item, state, run = release_tools
    monkeypatch.setattr(coordinator, "ROOT", tmp_path / "no-env")
    with pytest.raises(coordinator.SkipService, match="environment-values"):
        coordinator.deploy(component, "dev", item, source, ECR, run)
    assert state["calls"] == []


def test_connector_database_and_storage_isolation_is_required():
    old, new = deployment("old"), deployment("new", replicas=0)
    old["spec"]["template"]["spec"]["containers"][0]["env"].append({"name": "OLD_DB_NAME", "value": "old_db"})
    new["spec"]["template"]["spec"]["containers"][0]["env"].append({"name": "NEW_DB_NAME", "value": "replacement_db"})
    settings = {"database": "replacement_db", "oldDatabaseEnv": "OLD_DB_NAME", "databaseEnv": "NEW_DB_NAME"}
    coordinator.isolated_connector([old], [new], settings)
    new["spec"]["template"]["spec"]["containers"][0]["env"][-1]["value"] = "old_db"
    with pytest.raises(coordinator.ServiceError, match="isolation-unproven"):
        coordinator.isolated_connector([old], [new], settings)


def test_identity_evidence_cannot_be_reused_after_values_change_or_expiry(identity_inputs, tmp_path, monkeypatch):
    value = identity.check(*identity_inputs)
    file = tmp_path / "evidence.json"
    file.write_text(json.dumps(value))
    identity.evidence(file)
    monkeypatch.setattr(identity.time, "time", lambda: value["checkedAt"] + 3601)
    with pytest.raises(ValueError, match="expired"):
        identity.evidence(file)


@pytest.mark.parametrize("expired_job", [False, True])
def test_retire_command_cannot_run_without_acceptance(accepted, tmp_path, monkeypatch, expired_job):
    monkeypatch.setattr(cutover, "verify_backup", lambda p, environment="dev": "backup")
    (tmp_path / "backup.json").write_text('{"helmRevision": 2}')
    old, workloads, status, new_manifest, review, backup_hash = accepted
    if expired_job:
        old.append({"kind": "Job", "metadata": {"name": "farmer-connector-setup"}})
    calls = []
    pods = []
    def run(args):
        calls.append(args)
        if args[:2] == ["helm", "status"]:
            return json.dumps(status if args[2] == cutover.NEW else dict(status, name=cutover.OLD))
        if args[:3] == ["helm", "get", "manifest"]:
            return yaml.safe_dump_all(new_manifest if args[3] == cutover.NEW else old)
        if args[:3] == ["helm", "get", "hooks"]:
            return ""
        if args[:3] == ["kubectl", "get", "pods"]:
            return json.dumps({"items": pods})
        if args[:2] == ["kubectl", "get"]:
            if args[2] == "Job":
                assert "--ignore-not-found" in args
                return ""
            return json.dumps(workloads[0])
        if args[:2] == ["helm", "uninstall"]:
            return ""
        pytest.fail("Unexpected retirement command")
    review["odkApproval"] = False
    with pytest.raises(coordinator.ServiceError, match="acceptance-incomplete"):
        cutover.retire(tmp_path, review, run)
    assert not any("uninstall" in a for a in calls)
    review["odkApproval"] = True
    pods.append({"metadata": {"name": "farmer-connector-worker-terminating"}, "status": {"phase": "Running"}})
    with pytest.raises(coordinator.ServiceError, match="pods-not-stopped"):
        cutover.retire(tmp_path, review, run)
    assert not any("uninstall" in a for a in calls)
    pods.clear()
    cutover.retire(tmp_path, review, run)
    uninstall = [a for a in calls if "uninstall" in a]
    assert len(uninstall) == 1
    assert "--no-hooks" in uninstall[0] and "--keep-history" in uninstall[0]
    assert uninstall[0][2] == cutover.OLD
