import copy
import base64
import gzip
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_handoff", ROOT / "ci/connector/release_handoff.py")
handoff = importlib.util.module_from_spec(spec); spec.loader.exec_module(handoff)


@pytest.mark.parametrize("files", [None, [], [{"name": "retained.yaml", "data": base64.b64encode(b"retained").decode()}]])
def test_installed_chart_export_handles_absent_and_retained_files(tmp_path, monkeypatch, files):
    saved = {"chart": {"metadata": {"name": "connector", "version": "1.0.0"},
                       "values": {}, "templates": [], "files": files}}
    encoded = base64.b64encode(base64.b64encode(gzip.compress(json.dumps(saved).encode()))).decode()
    monkeypatch.setattr(handoff, "run", lambda args: json.dumps({"data": {"release": encoded}}))
    destination = tmp_path / "chart"
    handoff.export_chart(handoff.NEW, 1, destination)
    assert (destination / "Chart.yaml").exists()
    if files:
        assert (destination / "retained.yaml").read_text() == "retained"


@pytest.mark.parametrize("fault", [None, "image", "env", "delete", "secret", "running"])
def test_pausing_may_only_stop_existing_processes(fault):
    before = [{"kind": "Deployment", "metadata": {"name": "farmer-connector-worker"},
               "spec": {"replicas": 1, "template": {"spec": {"containers": [{"image": "preserved", "env": []}]}}}},
              {"kind": "Secret", "metadata": {"name": "retained"}, "data": {"password": "fixture"}}]
    after = copy.deepcopy(before); after[0]["spec"]["replicas"] = 0
    if fault == "image": after[0]["spec"]["template"]["spec"]["containers"][0]["image"] = "bad"
    if fault == "env": after[0]["spec"]["template"]["spec"]["containers"][0]["env"] = [{"name": "changed"}]
    if fault == "delete": after.pop()
    if fault == "secret": after[1]["data"] = {}
    if fault == "running": after[0]["spec"]["replicas"] = 1
    if fault:
        with pytest.raises(ValueError): handoff.replica_guard(before, after, handoff.OLD, {"worker": 0})
    else: handoff.replica_guard(before, after, handoff.OLD, {"worker": 0})


@pytest.mark.parametrize("fault", [None, "image", "secret", "queue", "replicas"])
def test_scheduler_must_use_the_same_worker_image_secret_and_queue(fault):
    worker = {"kind": "Deployment", "metadata": {"name": handoff.NEW+"-worker"}, "spec": {"replicas": 1,
              "template": {"spec": {"containers": [{"name": "connector-worker", "args": ["worker"], "image": "signed@digest",
                          "env": [{"name": "CONNECTOR_SIGNING_PRIVATE_KEY_PEM", "valueFrom": {"secretKeyRef": {"name": "retained", "key": "private-key.pem"}}}]}]}}}}
    beat = copy.deepcopy(worker); beat["metadata"]["name"] = handoff.NEW+"-beat"
    container = beat["spec"]["template"]["spec"]["containers"][0]
    container.update(name="connector-beat", args=["beat"])
    if fault == "image": container["image"] = "unsigned"
    if fault == "secret": container["env"] = []
    if fault == "queue": container["args"] = ["worker"]
    if fault == "replicas": beat["spec"]["replicas"] = 2
    if fault:
        with pytest.raises(ValueError): handoff.scheduler_guard([worker], [worker,beat])
    else: handoff.scheduler_guard([worker], [worker,beat])


@pytest.mark.parametrize("new_owner", [False, True])
@pytest.mark.parametrize("fault", [None, "host", "gateway", "destination", "secret"])
def test_route_handoff_preserves_environment_and_other_resources(new_owner, fault):
    route = {"kind": "VirtualService", "metadata": {"name": handoff.OLD}, "spec": {
        "hosts": ["connector-farmer-registry-development.oanstaging.com"], "gateways": ["internal"],
        "http": [{"route": [{"destination": {"host": handoff.OLD+"-api", "port": {"number": 80}}}]}]}}
    secret = {"kind": "Secret", "metadata": {"name": "retained"}, "data": {"password": "fixture"}}
    before = [secret] if new_owner else [secret, route]
    after = copy.deepcopy(before)
    new = copy.deepcopy(route); new["spec"]["http"][0]["route"][0]["destination"]["host"] = handoff.NEW+"-api"
    if new_owner: new["metadata"]["name"] = handoff.NEW; after.append(new)
    else: after[-1] = new
    if fault == "host": new["spec"]["hosts"] = ["other-registry.example"]
    if fault == "gateway": new["spec"]["gateways"] = ["public"]
    if fault == "destination": new["spec"]["http"][0]["route"][0]["destination"]["host"] = "commons-services"
    if fault == "secret": after[0]["data"] = {}
    if fault:
        with pytest.raises(ValueError): handoff.route_guard(before, after, new_owner)
    else: handoff.route_guard(before, after, new_owner)
