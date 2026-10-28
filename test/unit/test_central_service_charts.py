"""Central chart ports retain delivery ownership and reject unreviewed packages."""
import hashlib
import copy
import io
import json
from pathlib import Path
import tarfile

import pytest
import yaml

from test_service_coordination import coordinator, ECR, SHA, DIGEST
import central_chart

ROOT = Path(__file__).resolve().parents[2]


def package(name="farmer-registry-dashboard", version="0.1.2", dependencies=None):
    content = io.BytesIO()
    metadata = {"apiVersion": "v2", "name": name, "version": version}
    if dependencies is not None:
        metadata["dependencies"] = dependencies
    body = yaml.safe_dump(metadata).encode()
    with tarfile.open(fileobj=content, mode="w:gz") as archive:
        member = tarfile.TarInfo("farmer-registry-dashboard/Chart.yaml")
        member.size = len(body)
        archive.addfile(member, io.BytesIO(body))
    return content.getvalue()


def test_catalogue_extraction_preserves_exact_semantics_and_configuration_hash():
    original = yaml.safe_load((ROOT / "helm/openg2p-farmer-registry/values.yaml").read_text(encoding="utf-8"))["cossAddons"]
    extracted = yaml.safe_load((ROOT / "ci/services/catalogue.yaml").read_text(encoding="utf-8"))["cossAddons"]
    assert extracted == original
    assert coordinator.configuration_hash() == hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize("kind", ["registry-dashboard-api", "ui"])
def test_dev_build_layout_does_not_read_legacy_chart(tmp_path, monkeypatch, kind):
    component = next(c for c in coordinator.configuration() if (c.get("kind") == kind if kind != "ui" else c.get("chartSource") == "registry"))
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    provenance = coordinator.central_provenance(component, "dev")
    if kind == "ui":
        monkeypatch.setattr(central_chart, "download", lambda directory: Path(directory) / "verified.tgz")
    with coordinator.selected_chart(component, "dev", tmp_path) as (_, digest, selected):
        assert selected == provenance
        assert digest == coordinator.provenance_hash(provenance)
    assert not (tmp_path / "helm").exists()


def test_dev_api_build_records_central_archive_and_renderer_without_local_chart(tmp_path, monkeypatch):
    component = next(c for c in coordinator.configuration() if c.get("kind") == "registry-dashboard-api")
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    monkeypatch.setattr(coordinator, "checkout", lambda *a, **k: SHA)
    monkeypatch.setattr(coordinator, "build_image", lambda *a, **k: {"repository": ECR + "/" + component["imageRepository"], "tag": SHA[:12], "digest": DIGEST})
    result = coordinator.build(component, "dev", tmp_path, ECR, lambda args: "")
    assert result["deploymentChart"] == coordinator.dashboard_chart_provenance()
    assert result["chartHash"] == coordinator.provenance_hash(result["deploymentChart"])
    assert not (tmp_path / component["chart"]).exists()


@pytest.mark.parametrize("name,version,deps", [("other", "0.1.2", None), ("farmer-registry-dashboard", "0.1.3", None), ("farmer-registry-dashboard", "0.1.2", [{"name": "unreviewed"}])])
def test_identity_or_dependency_drift_rejected_even_if_checksum_matches(tmp_path, monkeypatch, name, version, deps):
    content = package(name, version, deps)
    pin = dict(central_chart.profile(), sha256=hashlib.sha256(content).hexdigest())
    monkeypatch.setattr(central_chart, "profile", lambda: pin)
    path = tmp_path / "chart.tgz"
    path.write_bytes(content)
    with pytest.raises(ValueError, match="identity or dependency"):
        central_chart.verify(path)


def test_corrupt_download_stops_before_any_build_or_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(central_chart.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"tampered"))
    component = next(c for c in coordinator.configuration() if c.get("chartSource") == "registry")
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    monkeypatch.setattr(coordinator, "checkout", lambda *a, **k: SHA)
    with pytest.raises(coordinator.ServiceError, match="download-or-checksum") as failure:
        coordinator.build(component, "dev", tmp_path, ECR, lambda *a: pytest.fail("Unexpected build/hook"))
    assert failure.value.provenance == {"commit": SHA}


def test_verified_ui_archive_is_given_to_existing_hook_rehearsal(tmp_path, monkeypatch):
    component = next(c for c in coordinator.configuration() if c.get("chartSource") == "registry")
    content = package()
    pin = dict(central_chart.profile(), sha256=hashlib.sha256(content).hexdigest())
    monkeypatch.setattr(central_chart, "profile", lambda: pin)
    monkeypatch.setattr(central_chart.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(content))
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    monkeypatch.setattr(coordinator, "checkout", lambda *a, **k: SHA)
    monkeypatch.setattr(coordinator, "build_image", lambda *a, **k: {"repository": ECR + "/" + component["imageRepository"], "tag": SHA[:12], "digest": DIGEST})
    def rehearsal(component, environment, record, chart, registry, run):
        assert chart.suffix == ".tgz" and central_chart.verify(chart) == pin
        assert record["chartHash"] == coordinator.provenance_hash(pin)
        assert component["release"] == "farmer-registry-dashboard"
        return {"executed": True}
    monkeypatch.setattr(coordinator, "dashboard_hook_rehearsal", rehearsal)
    result = coordinator.build(component, "dev", tmp_path, ECR, lambda *a: "")
    assert result["deploymentChart"] == pin and result["hookRehearsal"] == {"executed": True}


def test_ui_provenance_change_rejected_before_checkout_or_helm(tmp_path):
    component = next(c for c in coordinator.configuration() if c.get("chartSource") == "registry")
    pin = dict(central_chart.profile(), sha256="0" * 64)
    record = {"commit": SHA, "repository": ECR + "/" + component["imageRepository"], "tag": SHA[:12], "digest": DIGEST, "chartHash": "c" * 64, "deploymentChart": pin}
    with pytest.raises(coordinator.ServiceError, match="ui-approved-chart-provenance"):
        coordinator.deploy(component, "dev", record, tmp_path, ECR, lambda *a: pytest.fail("Unexpected tool call"))


def test_staging_selection_keeps_existing_charts_and_does_not_download(tmp_path, monkeypatch):
    monkeypatch.setattr(central_chart, "download", lambda *a: pytest.fail("Staging must not download dev addon"))
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    for component in coordinator.configuration(environment="staging"):
        if component.get("kind") == "connector":
            continue
        assert coordinator.central_provenance(component, "staging") is None
        assert coordinator.layout(component, tmp_path)[1] == ROOT / component["chart"]


def test_source_cleanup_is_blocked_until_remaining_ports_and_rehearsals():
    gate = json.loads((ROOT / "ci/services/chart-cleanup-gate.json").read_text(encoding="utf-8"))
    assert gate["retired"] is False
    assert len(gate["requiredEvidence"]) == 4
    for path in gate["requiredSources"] + gate["remainingConsumers"]:
        assert (ROOT / path).is_file(), "Retained chart cleanup requires reviewed consumer ports and fresh rehearsals: " + path


@pytest.mark.parametrize("race,hook_valid", [(False, True), (True, True), (False, False)])
def test_ui_central_deploy_retains_hook_image_resource_and_revision_guards(tmp_path, monkeypatch, race, hook_valid):
    from test_service_coordination import deployment
    component = next(c for c in coordinator.configuration() if c.get("chartSource") == "registry")
    content = package()
    pin = dict(central_chart.profile(), sha256=hashlib.sha256(content).hexdigest())
    monkeypatch.setattr(central_chart, "profile", lambda: pin)
    monkeypatch.setattr(central_chart.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(content))
    monkeypatch.setattr(coordinator, "ROOT", tmp_path)
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    values_path = tmp_path / "helm/environments/dev/services/farmer-registry-dashboard.yaml"
    values_path.parent.mkdir(parents=True)
    values_path.write_text(yaml.safe_dump({"_coordination": {"namespace": "farmer"}}))
    record = {"commit": SHA, "repository": ECR + "/" + component["imageRepository"], "tag": SHA[:12], "digest": DIGEST,
              "chartHash": coordinator.provenance_hash(pin), "deploymentChart": pin}
    record["hookRehearsal"] = {"commit": SHA, "digest": DIGEST, "chartHash": record["chartHash"], "environment": "dev",
        "valuesHash": hashlib.sha256(json.dumps({}, sort_keys=True).encode()).hexdigest(),
        "harnessHash": coordinator.chart_hash(tmp_path / "scripts/operations/dashboard"), "noExternalNetwork": True,
        "fixtureMode": "loopback-http-sqlite-kubectl-transport-shim",
        "hookJobs": [component["name"] + suffix for suffix in ("-ecr-refresh-init", "-iam-setup", "-chart-smoke")],
        "isolatedDatabases": True, "everyEnabledHook": hook_valid, "rerun": True, "failureRecovery": True}
    before = [deployment(component["release"])]
    after = copy.deepcopy(before)
    coordinator.pod(after[0])["containers"][0]["image"] = coordinator.artifact(component, record, ECR)
    hook = {"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": component["name"] + "-iam-setup", "annotations": {"helm.sh/hook": "pre-upgrade"}}}
    calls, state = [], {"upgraded": False, "status_reads": 0}
    monkeypatch.setattr(coordinator, "checkout", lambda *a, **k: SHA)
    def run(args):
        calls.append(args)
        if args[:2] == ["helm", "list"]:
            return json.dumps([{"name": component["release"]}])
        if args[:2] == ["helm", "status"]:
            state["status_reads"] += 1
            return json.dumps({"name": component["release"], "namespace": "farmer", "version": 13 if state["upgraded"] or (race and state["status_reads"] > 1) else 12, "info": {"status": "deployed"}})
        if args[:3] == ["helm", "get", "values"]:
            return "{}"
        if args[:3] == ["helm", "get", "manifest"]:
            return yaml.safe_dump_all(after if state["upgraded"] else before)
        if args[:3] == ["helm", "get", "hooks"]:
            return ""
        if args[:2] in (["helm", "template"], ["helm", "upgrade"]):
            assert args[2] == "farmer-registry-dashboard"
            assert central_chart.verify(Path(args[3])) == pin
            assert "--no-hooks" not in args
            if args[1] == "upgrade":
                assert {"--atomic", "--wait", "--wait-for-jobs"}.issubset(args)
                state["upgraded"] = True
            return yaml.safe_dump_all(after + [hook])
        pytest.fail("Unexpected dependency resolution or other command: " + str(args[:3]))
    if race or not hook_valid:
        with pytest.raises(coordinator.ServiceError, match="release-changed|incomplete-hook"):
            coordinator.deploy(component, "dev", record, tmp_path, ECR, run)
        assert not state["upgraded"]
    else:
        assert coordinator.deploy(component, "dev", record, tmp_path, ECR, run) == 13
        assert state["upgraded"]
    assert not any(call[:2] == ["helm", "dependency"] for call in calls)


def test_missing_application_layout_keeps_resolved_source_revision(tmp_path, monkeypatch):
    component = next(c for c in coordinator.configuration() if c.get("kind") == "registry-dashboard-api")
    monkeypatch.setattr(coordinator, "checkout", lambda *a, **k: SHA)
    with pytest.raises(coordinator.SkipService, match="missing-application-files") as failure:
        coordinator.build(component, "dev", tmp_path, ECR, lambda *a: pytest.fail("Unexpected build"))
    assert failure.value.provenance == {"commit": SHA}
