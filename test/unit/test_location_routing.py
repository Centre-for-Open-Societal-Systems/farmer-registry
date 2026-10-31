"""Dev Location reads use reviewed routes and service bindings."""
import copy

import pytest

from test_jenkins_deployment import ECR, TAG, deployment, release


def test_prepare_repairs_saved_dev_routes_and_approved_service_binding(release):
    reference = {"secretKeyRef": {"name": "existing-client", "key": "client_secret"}}
    values = {"global": {"registryHostname": "farmer-registry-development.oanstaging.com"},
              "registry": {"staffApi": {"envVars": {
                  "REGISTRY_STAFF_PORTAL_API_MASTER_DATA_API_URL": "http://wrong-namespace",
                  "REGISTRY_STAFF_PORTAL_API_MASTER_DATA_CLIENT_ID": "existing-client"},
                  "envVarsFrom": {"REGISTRY_STAFF_PORTAL_API_MASTER_DATA_CLIENT_SECRET": reference,
                                  "REGISTRY_STAFF_PORTAL_API_DB_PASSWORD": reference}}}}
    previous = copy.deepcopy(values)
    prepared = deployment.prepare(values, release[0], ECR, TAG)
    staff = prepared["registry"]["staffApi"]
    assert staff["envVars"]["REGISTRY_STAFF_PORTAL_API_MASTER_DATA_API_URL"] == "http://commons-services-master-data-api.commons.svc.cluster.local"
    assert staff["envVars"]["REGISTRY_STAFF_PORTAL_API_MASTER_DATA_TOKEN_URL"].startswith("https://keycloak-development.oanstaging.com/")
    assert staff["envVars"]["REGISTRY_STAFF_PORTAL_API_MASTER_DATA_CLIENT_ID"] == "farmer-registry-staff-portal"
    assert staff["envVarsFrom"]["REGISTRY_STAFF_PORTAL_API_MASTER_DATA_CLIENT_SECRET"] == {
        "secretKeyRef": {"name": "farmer-registry-staff-portal", "key": "client_secret", "optional": False}}
    # Installed Secret wiring takes precedence over stale saved values.
    assert staff['envVarsFrom']['REGISTRY_STAFF_PORTAL_API_DB_PASSWORD'] == {
        'secretKeyRef': {'name': 'farmer-registry', 'key': 'farmer-registry-db-user'}}
    assert values == previous
    assert "keycloakBaseUrl" not in prepared["global"]
    assert deployment.location_overlay("staging-legacy") == {}
    staged = deployment.location_overlay("staging")
    assert staged["global"]["masterDataTokenUrl"] == "https://keycloak.oanstaging.com/realms/staff/protocol/openid-connect/token"
    assert "development" not in str(staged)


def test_guard_allows_only_reviewed_dev_route_changes(release):
    before, after = release
    entry = {"name": "REGISTRY_STAFF_PORTAL_API_MASTER_DATA_API_URL", "value": "http://old"}
    deployment.pod(before[0])["containers"][0]["env"].append(entry)
    deployment.validate(before, after, ECR, TAG)
    changed = deployment.pod(after[0])["containers"][0]["env"]
    next(e for e in changed if e["name"] == entry["name"])["value"] = "http://unreviewed"
    with pytest.raises(ValueError, match="environment/Secret reference changed"):
        deployment.validate(before, after, ECR, TAG)


def test_missing_ui_route_is_rejected(release):
    before, after = release
    ui = next(d for d in after if d["kind"] == "Deployment" and d["metadata"]["name"].endswith("-staff-portal-ui"))
    deployment.pod(ui)["containers"][0]["env"] = []
    with pytest.raises(ValueError, match="Master Data routing was not rendered"):
        deployment.validate(before, after, ECR, TAG)


@pytest.mark.parametrize("failure", ["missing", "wrong"])
def test_dev_promotion_requires_approved_service_binding(release, failure):
    before, after = release
    env = deployment.pod(after[0])["containers"][0]["env"]
    name = "REGISTRY_STAFF_PORTAL_API_MASTER_DATA_CLIENT_SECRET"
    if failure == "missing":
        env[:] = [entry for entry in env if entry["name"] != name]
    else:
        next(entry for entry in env if entry["name"] == name)["valueFrom"]["secretKeyRef"]["optional"] = True
    with pytest.raises(ValueError, match="Master Data credentials were not rendered"):
        deployment.validate(before, after, ECR, TAG)


def test_dev_staff_ui_allows_the_location_map_hosts():
    env = deployment.location_env("staff-portal-ui")
    assert "https://tile.openstreetmap.org" in env["CSP_SRC_IMG"].split()
    assert "https://minio-farmer.development.oanstaging.com" in env["CSP_SRC_IMG"].split()
    assert "https://api.open-meteo.com" in env["CSP_SRC_CONNECT"].split()
