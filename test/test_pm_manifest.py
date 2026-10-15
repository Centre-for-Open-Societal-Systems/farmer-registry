"""Reject the observed issuer/routing regressions before a Commons rollout."""
import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pm_guard", ROOT / "ci/gen2/check_pm_manifest.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def deployment(name, env):
    return {"kind": "Deployment", "metadata": {"name": name}, "spec": {"template": {
        "spec": {"containers": [{"env": [{"name": k, "value": v} for k, v in env.items()]}]}}}}


def route(name, host):
    return {"kind": "VirtualService", "metadata": {"name": name}, "spec": {
        "hosts": [host], "http": [{"route": [{"destination": {"host": name}}]}]}}


@pytest.fixture
def manifests():
    overlay = yaml.safe_load((ROOT / "ci/gen2/commons-pm-new-dev.values.yaml").read_text())
    pm = overlay["partner-management"]
    return [deployment("commons-services-pm-staff-portal-api", pm["staffPortalApi"]["envVars"]),
            deployment("commons-services-pm-staff-portal-ui", {
                **pm["staffPortalUi"]["envVars"],
                "IAM_URL": "http://commons-services-iam-staff-portal-api",
                "STAFF_PORTAL_API_URL": "http://commons-services-pm-staff-portal-api",
                "REDIRECT_URL": "https://partner-management.commons-dev.oanstaging.com"}),
            route("commons-services-pm-staff-portal-api", pm["staffPortalApi"]["istio"]["virtualservice"]["host"]),
            route("commons-services-iam-staff-portal-api", guard.IAM_HOST)]


def test_overlay_passes(manifests):
    guard.validate(manifests)


@pytest.mark.parametrize("field,value", [
    ("PARTNER_MANAGER_AUTH_DEFAULT_ISSUERS", '["http://commons-keycloak:80/realms/staff"]'),
    ("COMMON_AUTH_DEFAULT_JWKS_URLS", '[]'),
    ("PARTNER_MANAGER_AUTH_ENABLED", "false"),
    ("PARTNER_MANAGER_AUTH_ADMIN_ROLE", ""),
])
def test_auth_regressions_rejected(manifests, field, value):
    env = manifests[0]["spec"]["template"]["spec"]["containers"][0]["env"]
    next(e for e in env if e["name"] == field)["value"] = value
    with pytest.raises(ValueError):
        guard.validate(manifests)


def test_shared_iam_host_collision_rejected(manifests):
    manifests[2]["spec"]["hosts"] = [guard.IAM_HOST]
    with pytest.raises(ValueError):
        guard.validate(manifests)


def test_duplicate_route_rejected(manifests):
    duplicate = copy.deepcopy(manifests[2])
    duplicate["metadata"]["name"] = "unexpected-route"
    manifests.append(duplicate)
    with pytest.raises(ValueError):
        guard.validate(manifests)


def test_cluster_only_logout_rejected(manifests):
    env = manifests[1]["spec"]["template"]["spec"]["containers"][0]["env"]
    next(e for e in env if e["name"] == "KEYCLOAK_LOGOUT_URL")["value"] = "http://commons-keycloak/logout"
    with pytest.raises(ValueError):
        guard.validate(manifests)
