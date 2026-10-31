import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("partner_rollout", ROOT / "scripts/operations/registry/deploy_partner_only.py")
rollout = importlib.util.module_from_spec(spec); spec.loader.exec_module(rollout)


@pytest.mark.parametrize("change", [None, "worker", "secret", "env", "job"])
def test_signing_rollout_can_only_change_partner_image(change):
    def deployment(name):
        return {"kind": "Deployment", "metadata": {"name": name}, "spec": {"template": {"spec": {"containers": [{"name": name, "image": "old", "env": []}]}}}}
    before = [deployment("farmer-registry-partner-api"), deployment("farmer-registry-celery-worker"),
              {"kind": "Secret", "metadata": {"name": "retained"}, "data": {"password": "fixture"}}]
    after = copy.deepcopy(before)
    after[0]["spec"]["template"]["spec"]["containers"][0]["image"] = "signed@digest"
    if change == "worker": after[1]["spec"]["template"]["spec"]["containers"][0]["image"] = "unexpected"
    if change == "secret": after[2]["data"]["password"] = "changed"
    if change == "env": after[0]["spec"]["template"]["spec"]["containers"][0]["env"].append({"name": "changed", "value": "bad"})
    if change == "job": after.append({"kind": "Job", "metadata": {"name": "setup"}})
    if change:
        with pytest.raises(ValueError): rollout.guard(before, after, "signed@digest")
    else: rollout.guard(before, after, "signed@digest")
