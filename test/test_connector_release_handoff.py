import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_handoff", ROOT / "ci/connector/release_handoff.py")
handoff = importlib.util.module_from_spec(spec); spec.loader.exec_module(handoff)


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
