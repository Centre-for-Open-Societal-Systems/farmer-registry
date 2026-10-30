"""Operational ports select verified archives without broadening image-only guards."""
import copy
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from test_worker_rollout import rollout as worker
from test_signing_rollout import rollout as partner

approved = worker.approved_chart
ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
DIGEST = "b" * 64


@pytest.mark.parametrize("installed", ["legacy-1.0", None])
def test_wrong_installed_chart_blocks_before_any_download(tmp_path, monkeypatch, installed):
    monkeypatch.setattr(approved.urllib.request, "urlopen", lambda *a, **k: pytest.fail("Unexpected download"))
    with pytest.raises(ValueError, match="already-adopted"):
        approved.prepare(tmp_path, {}, [], installed)


def test_corrupt_archive_never_reconciles_private_values(tmp_path, monkeypatch):
    pin = approved.profile()
    monkeypatch.setattr(approved.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"corrupt"))
    monkeypatch.setattr(approved, "reconcile_dev", lambda *a: pytest.fail("Unexpected reconciliation"))
    with pytest.raises(ValueError, match="verification failed"):
        approved.prepare(tmp_path, {}, [], pin["name"] + "-" + pin["version"])


def test_verified_archive_is_selected_and_prior_process_environment_restored(tmp_path, monkeypatch):
    pin = approved.profile()
    monkeypatch.setattr(approved.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"verified fixture"))
    seen = []
    monkeypatch.setattr(approved, "verify", lambda archive: seen.append(Path(archive).read_bytes()))
    monkeypatch.setenv("OAN_CHART_ARCHIVE", "previous-owned-archive")
    def reconcile(values, before):
        import os
        assert Path(os.environ["OAN_CHART_ARCHIVE"]).is_file()
        values["preserved"] = True
    monkeypatch.setattr(approved, "reconcile_dev", reconcile)
    values = {}
    chart, provenance = approved.prepare(tmp_path, values, [], pin["name"] + "-" + pin["version"])
    import os
    assert seen == [b"verified fixture"] and values["preserved"]
    assert os.environ["OAN_CHART_ARCHIVE"] == "previous-owned-archive"
    assert provenance["sha256"] == pin["sha256"] and len(provenance["adapterSha256"]) == 64
    assert chart.suffix == ".tgz"


def test_renderer_rejects_unverified_archive_without_emitting_manifest(tmp_path):
    archive = tmp_path / "corrupt.tgz"
    archive.write_bytes(b"corrupt")
    values = tmp_path / "values.yaml"
    values.write_text("{}")
    renderer = approved.renderer(tmp_path, archive, values)
    result = subprocess.run([sys.executable, str(renderer)], input="kind: Job\nmetadata: {name: setup}\n", text=True, capture_output=True, check=False)
    assert result.returncode != 0 and not result.stdout
    assert result.stderr.strip() == "Approved image-only renderer rejected input"


@pytest.mark.parametrize("tool,role", [(worker, "worker"), (partner, "partner")])
def test_apply_is_blocked_by_a_foreign_chart_pin_before_any_cluster_call(tmp_path, monkeypatch, tool, role):
    import oan_chart
    image_role = "celery" if role == "worker" else "partner-api"
    image = f"123456789012.dkr.ecr.ap-south-1.amazonaws.com/openg2p/farmer-registry/{image_role}:{SHA[:12]}@sha256:{DIGEST}"
    monkeypatch.setattr(sys, "argv", ["rollout", "--image", image, "--commit", SHA, "--output", str(tmp_path / "out.json"), "--apply"])
    monkeypatch.setattr(tool, "command", lambda *a: pytest.fail("Unexpected cluster call"))
    monkeypatch.setattr(oan_chart, "profile", lambda *a: {**approved.profile(), "environment": "staging"})
    with pytest.raises(ValueError, match="Deployment blocked"):
        tool.main()


@pytest.mark.parametrize("tool,role,race", [(worker, "worker", False), (worker, "worker", True), (partner, "partner", False), (partner, "partner", True)])
@pytest.mark.parametrize("apply", [False, True])
def test_main_uses_approved_archive_preserves_permitted_changes_and_blocks_races(tmp_path, monkeypatch, tool, role, race, apply):
    image_role = "celery" if role == "worker" else "partner-api"
    image = f"123456789012.dkr.ecr.ap-south-1.amazonaws.com/openg2p/farmer-registry/{image_role}:{SHA[:12]}@sha256:{DIGEST}"
    output = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["rollout", "--image", image, "--commit", SHA, "--output", str(output)] + (["--apply"] if apply else []))
    monkeypatch.setattr(approved, "require_deployable", lambda environment: environment == "dev")
    selected = "celeryWorker" if role == "worker" else "partnerApi"
    target = "farmer-registry-celery-worker" if role == "worker" else "farmer-registry-partner-api"
    env = [{"name": worker.TOKEN_NAME, "value": "old-token-url"}] if role == "worker" else []
    before = [{"kind": "Deployment", "metadata": {"name": target}, "spec": {"template": {"spec": {"containers": [{"name": role, "image": "old:v1", "env": env}]}}}},
              {"kind": "Secret", "metadata": {"name": "retained"}, "data": {"password": "synthetic"}}]
    after = copy.deepcopy(before)
    after[0]["spec"]["template"]["spec"]["containers"][0]["image"] = image
    if role == "worker":
        after[0]["spec"]["template"]["spec"]["containers"][0]["env"][0]["value"] = worker.TOKEN_URL
    pin = approved.profile()
    chart = tmp_path / "approved.tgz"
    chart.write_bytes(b"verified fixture")
    def prepare(directory, values, previous, installed):
        assert installed == pin["name"] + "-" + pin["version"] and previous == before
        # Reconciliation precedes the narrowly permitted operation changes.
        values.setdefault("registry", {}).setdefault(selected, {})["envVars"] = {worker.TOKEN_NAME: "old-token-url"}
        return chart, {"sha256": pin["sha256"]}
    monkeypatch.setattr(approved, "prepare", prepare)
    monkeypatch.setattr(approved, "renderer", lambda *a: tmp_path / "renderer")
    calls, state = [], {"status": 0, "upgraded": False}
    def command(args):
        calls.append(args)
        if args[:2] == ["helm", "status"]:
            state["status"] += 1
            return json.dumps({"version": 13 if state["upgraded"] or (race and state["status"] > 1) else 12, "info": {"status": "deployed"}})
        if args[:2] == ["helm", "list"]:
            return json.dumps([{"name": "farmer-registry", "chart": pin["name"] + "-" + pin["version"]}])
        if args[:3] == ["helm", "get", "values"]:
            return yaml.safe_dump({"global": {"registryHostname": "farmer-registry-development.oanstaging.com"}})
        if args[:3] == ["helm", "get", "manifest"]:
            return yaml.safe_dump_all(after if state["upgraded"] else before)
        if args[:2] == ["helm", "upgrade"]:
            assert apply and not race and args[3] == str(chart)
            assert {"--atomic", "--wait", "--timeout", "10m", "--no-hooks", "--post-renderer"}.issubset(args)
            state["upgraded"] = True
            return ""
        if args[:2] == ["helm", "template"]:
            assert args[3] == str(chart)
            assert {"--no-hooks", "--is-upgrade", "--dry-run=server", "--post-renderer"}.issubset(args)
            values = yaml.safe_load(Path(args[args.index("-f") + 1]).read_text())
            assert values["registry"][selected]["image"]["tag"] == SHA[:12] + "@sha256:" + DIGEST
            if role == "worker":
                assert values["registry"][selected]["envVars"][worker.TOKEN_NAME] == worker.TOKEN_URL
            return yaml.safe_dump_all(after)
        pytest.fail("Unexpected deployment or dependency command: " + str(args[:3]))
    monkeypatch.setattr(tool, "command", command)
    if race:
        with pytest.raises(ValueError, match="release changed"):
            tool.main()
        assert not output.exists()
    else:
        tool.main()
        result = json.loads(output.read_text())
        assert result["outcome"] == ("deployed" if apply else "validated") and result["setupJobsExecuted"] is False
        assert state["upgraded"] is apply
        assert result["chartProvenance"]["sha256"] == pin["sha256"]
    assert not any(call[:2] in (["helm", "dependency"], ["helm", "repo"]) for call in calls)
