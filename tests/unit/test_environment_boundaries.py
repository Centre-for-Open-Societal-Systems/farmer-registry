"""Environment dispatch and credentials must not cross the dev/staging boundary."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("delivery_environments", ROOT / "ci/environments.py")
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


@pytest.mark.parametrize("environment,namespace", [("dev", "farmer"), ("staging", "far")])
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


def test_staging_requires_explicit_gate_and_never_uses_dev_deploy_or_connector_cutover():
    pipeline = (ROOT / "ci/pipelines/staging.groovy").read_text()
    assert "name: 'DEPLOY_STAGING', defaultValue: false" in pipeline
    assert "env.BRANCH_NAME != 'staging' || env.CHANGE_ID" in pipeline
    assert "Legacy staging Dockerfile missing" in pipeline
    assert "ci/deploy/staging-legacy.sh" in pipeline
    assert "ci/deploy/deploy-dev.sh" not in pipeline
    assert "connector_cutover" not in pipeline
    shell = (ROOT / "ci/deploy/staging-legacy.sh").read_text()
    assert "helm upgrade --install" not in shell
    assert "python ci/environments.py staging --status" in shell
