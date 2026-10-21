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


def test_staging_requires_rehearsal_and_shared_rc_path_without_automatic_cutover():
    pipeline = (ROOT / "ci/pipelines/staging.groovy").read_text()
    assert "name: 'DEPLOY_STAGING', defaultValue: false" in pipeline
    assert "env.BRANCH_NAME != 'staging' || env.CHANGE_ID" in pipeline
    assert "staging-farmer-rehearsal" in pipeline
    assert "ci/deploy/deploy-rc.sh" in pipeline
    assert "staging-legacy" not in pipeline
    assert "ci/deploy/deploy-dev.sh" not in pipeline
    assert "connector_cutover" not in pipeline
    shell = (ROOT / "ci/deploy/deploy-rc.sh").read_text()
    assert "helm upgrade --install" not in shell
    assert "guard cutover" in shell
    assert "dev:farmer" in shell and "staging:far" in shell
