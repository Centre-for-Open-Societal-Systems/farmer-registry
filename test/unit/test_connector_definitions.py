"""The farmer-connector-definitions release: declared Farmer connector definitions, applied like crop and livestock."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "helm/farmer-connector-definitions"
IMAGE = "379220350808.dkr.ecr.ap-south-1.amazonaws.com/openg2p/farmer-registry/registry-connector:t@sha256:" + "a" * 64
# sha256 of ci/connector/chart/files/apply_definitions.py on livestock-registry develop (7e2729a), which is also
# ci/deploy/connector-chart/files/apply_definitions.py on cropsown-regsitry develop. Change all three together.
APPLY_DEFINITIONS_SHA256 = "ec520a7a0832d2eabb98d98e9634936a8de8c1edf1b983c3e595fb41e9db0587"
needs_helm = pytest.mark.skipif(not shutil.which("helm"), reason="Helm required")


def test_apply_definitions_is_the_crop_and_livestock_script():
    content = (CHART / "files/apply_definitions.py").read_bytes()
    assert b"\r" not in content
    assert hashlib.sha256(content).hexdigest() == APPLY_DEFINITIONS_SHA256


@pytest.mark.parametrize("environment", ["dev", "staging"])
def test_environment_definitions_name_secrets_only(environment):
    values = yaml.safe_load((ROOT / f"helm/environments/{environment}/farmer-connector-definitions.yaml").read_text())
    assert values["adminAuth"]["tokenUrl"].endswith("/realms/staff/protocol/openid-connect/token")
    (odk,) = values["definitions"]
    assert odk["name"] == "Farmer Registry - ODK Central Ingestion"
    assert set(odk) & {"webhook_secret", "auth_secret_json"} == set()
    for ref in odk["auth_secret_from"].values():
        assert set(ref) == {"secret", "key"}
    host = {"dev": "https://odk-central.development.oanstaging.com", "staging": "https://odk-central.qa.oanstaging.com"}
    assert odk["source_config"]["base_url"] == host[environment]
    assert odk["source_config"]["form_id"] == "farmer_profile"


def test_staging_stays_paused_until_the_geography_cutover():
    values = yaml.safe_load((ROOT / "helm/environments/staging/farmer-connector-definitions.yaml").read_text())
    assert values["definitions"][0]["paused"] is True


def render(environment, *extra):
    return subprocess.run(["helm", "template", "farmer-connector-definitions", str(CHART), "-n", "farmer",
                           "-f", str(ROOT / f"helm/environments/{environment}/farmer-connector-definitions.yaml"),
                           *extra], capture_output=True, text=True, timeout=60)


@needs_helm
@pytest.mark.parametrize("environment", ["dev", "staging"])
def test_chart_renders_the_hook_with_the_running_connector_image(environment):
    result = render(environment, "--set-string", "image=" + IMAGE)
    assert result.returncode == 0, result.stderr
    items = {(d["kind"], d["metadata"]["name"]): d for d in yaml.safe_load_all(result.stdout) if d}
    assert set(items) == {("ServiceAccount", "farmer-registry-connector-definitions"),
                          ("ConfigMap", "farmer-registry-connector-definitions"),
                          ("Job", "farmer-registry-connector-definitions")}
    job = items["Job", "farmer-registry-connector-definitions"]
    assert job["metadata"]["annotations"]["helm.sh/hook"] == "post-install,post-upgrade"
    pod = job["spec"]["template"]["spec"]
    assert pod["serviceAccountName"] == "farmer-registry-connector-definitions"
    (container,) = pod["containers"]
    assert container["image"] == IMAGE
    env = {e["name"]: e for e in container["env"]}
    assert set(env) == {"CD_CONFIG", "CD_0_AUTH_EMAIL", "CD_0_AUTH_PASSWORD"}
    assert all("value" not in env[name] for name in ("CD_0_AUTH_EMAIL", "CD_0_AUTH_PASSWORD"))
    config = items["ConfigMap", "farmer-registry-connector-definitions"]["data"]
    assert config["apply_definitions.py"].strip() == (CHART / "files/apply_definitions.py").read_text().strip()
    declared = json.loads(config["definitions.json"])
    assert declared["apiBase"] == "http://farmer-registry-connector-api.farmer.svc.cluster.local:80"
    assert declared["adminAuth"]["clientSecret"] == {"namespace": "commons", "name": "registry-connector", "key": "client_secret"}


@needs_helm
def test_chart_refuses_to_render_without_an_image():
    result = render("dev")
    assert result.returncode != 0
    assert "image is required" in result.stderr


def test_both_pipelines_apply_the_definitions_after_the_services_deploy():
    for environment in ("dev", "staging"):
        pipeline = (ROOT / f"ci/pipelines/{environment}.groovy").read_text()
        services = pipeline.index("run-container.sh deploy")
        definitions = pipeline.rindex(f"bash ci/deploy/connector-definitions.sh {environment}")
        assert services < definitions


def test_a_staging_promotion_applies_the_definitions():
    """A merge into staging only promotes (the services deploy is an operator action), so the promote stage
    applies the declared definitions itself, after the registry is promoted."""
    pipeline = (ROOT / "ci/pipelines/staging.groovy").read_text()
    promote = pipeline.index("stage('Promote and deploy')")
    registry_deploy = pipeline.index("stage('Deploy (registry)')")
    stage = pipeline[promote:registry_deploy]
    assert stage.index("bash ci/deploy/promote-staging.sh") < stage.index("bash ci/deploy/connector-definitions.sh staging")
