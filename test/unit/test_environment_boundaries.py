"""Environment dispatch and credentials must not cross the dev/staging boundary."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("delivery_environments", ROOT / "ci/environments.py")
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


@pytest.mark.parametrize("environment,namespace", [("dev", "farmer"), ("staging", "farmer")])
def test_existing_environment_requires_matching_namespace_and_hostname(environment, namespace):
    config = delivery.configuration(environment)
    status = {"name": "farmer-registry", "namespace": namespace, "info": {"status": "deployed"}}
    values = {"global": {"registryHostname": config["registryHostname"]}}
    delivery.validate_release(environment, status, values)
    for field, value in [("namespace", "commons"), ("namespace", "far" if namespace == "farmer" else "farmer"), ("name", "other")]:
        altered = copy.deepcopy(status)
        altered[field] = value
        with pytest.raises(ValueError):
            delivery.validate_release(environment, altered, values)
    other = "staging" if environment == "dev" else "dev"
    with pytest.raises(ValueError):
        delivery.validate_release(environment, status, {"global": {"registryHostname": delivery.configuration(other)["registryHostname"]}})


def test_staging_requires_rehearsal_and_shared_rc_path_without_automatic_cutover():
    pipeline = (ROOT / "ci/pipelines/staging.groovy").read_text(encoding="utf-8")
    assert "name: 'DEPLOY_STAGING', defaultValue: false" in pipeline
    assert "choices: ['validate-only', 'fresh-install', 'deploy']" in pipeline
    assert "params.DEPLOY_STAGING ? params.DELIVERY_ACTION : 'validate-only'" in pipeline
    assert "HELM_NAMESPACE = 'farmer'" in pipeline and "label 'vpn-agent2'" in pipeline
    assert "staging-farmer-kubeconfig" in pipeline and "ci/deploy/fresh-install-staging.sh" in pipeline
    assert "env.BRANCH_NAME != 'staging' || env.CHANGE_ID" in pipeline
    assert "staging-farmer-rehearsal" in pipeline
    assert "ci/deploy/deploy-rc.sh" in pipeline
    assert "staging-legacy" not in pipeline
    assert "ci/deploy/deploy-dev.sh" not in pipeline
    assert "connector_cutover" not in pipeline
    shell = (ROOT / "ci/deploy/deploy-rc.sh").read_text(encoding="utf-8")
    assert "helm upgrade --install" not in shell
    assert "guard cutover" in shell
    assert "dev:farmer" in shell and "staging:farmer" in shell and "staging:far)" not in shell


def test_staging_contract_is_the_oan_install_beside_the_legacy_release():
    staging = delivery.configuration("staging")
    assert (staging["namespace"], staging["release"], staging["platform"]) == ("farmer", "farmer-registry", "1.2.2-rc.614")
    assert staging["registryHostname"] == "farmer-registry.oanstaging.com"
    assert staging["staffIssuer"] == "https://keycloak.oanstaging.com/realms/staff"
    assert (staging["registryDatabase"], staging["idGeneratorDatabase"], staging["connectorDatabase"]) == (
        "farmer_registry", "farmer_registry_idgen", "farmer_connector_v2")
    assert staging["apiServers"] == ["https://10.0.1.212:6443", "https://52.66.116.220:6443"]
    legacy = delivery.configuration("staging-legacy")
    assert legacy["namespace"] == "far" and legacy["registryDatabase"].endswith("_far")
    assert delivery.namespace("staging") != delivery.namespace("staging-legacy")


def test_staging_contract_must_match_the_pinned_platform():
    import json
    pin = json.loads((ROOT / "ci/deploy/oan-chart-staging.json").read_text(encoding="utf-8"))
    contract = delivery.configuration("staging")
    assert (pin["environment"], pin["namespace"], pin["release"], pin["platformVersion"]) == (
        "staging", contract["namespace"], contract["release"], contract["platform"])
