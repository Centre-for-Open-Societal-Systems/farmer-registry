"""A worker hotfix must preserve every other release resource and credential."""
import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("worker_rollout", Path(__file__).resolve().parents[1] / "ci/jenkins/deploy-worker-only.py")
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)


def manifests():
    old = [{"kind": "Deployment", "metadata": {"name": rollout.WORKER[1]},
            "spec": {"template": {"spec": {"containers": [{"name": "worker", "image": "old:v1", "env": [
                {"name": rollout.TOKEN_NAME, "value": "http://commons-keycloak/realms/staff/token"},
                {"name": "DB_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "existing", "key": "password"}}}]}]}}}},
           {"kind": "Secret", "metadata": {"name": "existing"}, "data": {"password": "private-fixture"}},
           {"kind": "Deployment", "metadata": {"name": "farmer-registry-dashboard-api"}, "spec": {"image": "dashboard:v1"}},
           {"kind": "PersistentVolumeClaim", "metadata": {"name": "storage"}, "spec": {"storageClassName": "existing"}},
           {"kind": "Job", "metadata": {"name": "old-setup-11"}}]
    new = copy.deepcopy(old[:-1])
    container = new[0]["spec"]["template"]["spec"]["containers"][0]
    container["image"] = "new@sha256:tested"
    container["env"][0]["value"] = rollout.TOKEN_URL
    return old, new


def test_worker_image_and_verified_token_url_are_the_only_allowed_changes():
    before, after = manifests()
    rollout.guard(before, after, "new@sha256:tested")


def test_postgres_checker_may_inherit_only_the_same_verified_token_url():
    before, after = manifests()
    checker = {"name": "postgres-checker", "image": "checker:v1",
               "env": [{"name": rollout.TOKEN_NAME, "value": "http://commons-keycloak/realms/staff/token"}]}
    before[0]["spec"]["template"]["spec"]["initContainers"] = [checker]
    updated = copy.deepcopy(checker)
    updated["env"][0]["value"] = rollout.TOKEN_URL
    after[0]["spec"]["template"]["spec"]["initContainers"] = [updated]
    rollout.guard(before, after, "new@sha256:tested")
    updated["image"] = "unreviewed:v2"
    with pytest.raises(ValueError):
        rollout.guard(before, after, "new@sha256:tested")


@pytest.mark.parametrize("mutation", ["secret", "dashboard", "storage", "credential-reference", "removal", "job", "issuer", "namespace"])
def test_worker_rollout_rejects_unrelated_changes(mutation):
    before, after = manifests()
    if mutation == "secret": after[1]["data"]["password"] = "changed"
    if mutation == "dashboard": after[2]["spec"]["image"] = "dashboard:v2"
    if mutation == "storage": after[3]["spec"]["storageClassName"] = "other"
    if mutation == "credential-reference": after[0]["spec"]["template"]["spec"]["containers"][0]["env"][1]["valueFrom"]["secretKeyRef"]["name"] = "other"
    if mutation == "removal": after.pop()
    if mutation == "job": after.append({"kind": "Job", "metadata": {"name": "new-setup"}})
    if mutation == "issuer": after[0]["spec"]["template"]["spec"]["containers"][0]["env"][0]["value"] = "https://other.example/token"
    if mutation == "namespace": after[1]["metadata"]["namespace"] = "commons"
    with pytest.raises(ValueError):
        rollout.guard(before, after, "new@sha256:tested")
