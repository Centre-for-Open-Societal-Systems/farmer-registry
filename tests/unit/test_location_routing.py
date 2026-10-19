"""G2R-333/361/362: dev Location reads must reach Commons, preserving credentials."""
import copy

import pytest

from tests.unit.test_jenkins_deployment import ECR, TAG, deployment, release


def test_prepare_repairs_saved_dev_routes_without_changing_credentials(release):
    reference = {"secretKeyRef": {"name": "existing-client", "key": "client_secret"}}
    values = {"global": {"registryHostname": "farmer-registry-development.oanstaging.com"},
              "registry": {"staffApi": {"envVars": {
                  "REGISTRY_STAFF_PORTAL_API_MASTER_DATA_API_URL": "http://wrong-namespace",
                  "REGISTRY_STAFF_PORTAL_API_MASTER_DATA_CLIENT_ID": "existing-client"},
                  "envVarsFrom": {"REGISTRY_STAFF_PORTAL_API_MASTER_DATA_CLIENT_SECRET": reference}}}}
    previous = copy.deepcopy(values)
    prepared = deployment.prepare(values, release[0], ECR, TAG)
    staff = prepared["registry"]["staffApi"]
    assert staff["envVars"]["REGISTRY_STAFF_PORTAL_API_MASTER_DATA_API_URL"] == "http://commons-services-master-data-api.commons.svc.cluster.local"
    assert staff["envVars"]["REGISTRY_STAFF_PORTAL_API_MASTER_DATA_TOKEN_URL"].startswith("https://keycloak-development.oanstaging.com/")
    assert staff["envVars"]["REGISTRY_STAFF_PORTAL_API_MASTER_DATA_CLIENT_ID"] == "existing-client"
    assert staff["envVarsFrom"]["REGISTRY_STAFF_PORTAL_API_MASTER_DATA_CLIENT_SECRET"] == reference
    assert values == previous
    assert "keycloakBaseUrl" not in prepared["global"]
    assert deployment.location_overlay("staging") == {}


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
