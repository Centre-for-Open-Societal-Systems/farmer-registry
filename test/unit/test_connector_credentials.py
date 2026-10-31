"""Run with Helm/OpenSSL installed; generated credentials never enter output."""
import base64
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "helm/farmer-connector-credentials"
pytestmark = pytest.mark.skipif(not shutil.which("helm"), reason="Helm required")


def render(namespace="farmer", release="farmer-connector-credentials"):
    return subprocess.run(["helm", "template", release, str(CHART), "-n", namespace],
                          capture_output=True, text=True, timeout=60)


def test_generated_credentials_are_isolated_retained_and_usable():
    result = render()
    assert result.returncode == 0, "Credential chart did not render"
    items = list(yaml.safe_load_all(result.stdout))
    assert len(items) == 2
    data = {}
    for item in items:
        assert item["kind"] == "Secret"
        assert item["metadata"]["namespace"] == "farmer"
        assert item["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
        data[item["metadata"]["name"]] = item["data"]
    password = base64.b64decode(data["farmer-connector-v2-db"]["password"])
    assert len(password) == 48 and password.isalnum()
    key = base64.b64decode(data["farmer-connector-v2-signing"]["private-key.pem"])
    assert b"PRIVATE KEY" in key
    checked = subprocess.run(["openssl", "pkey", "-check", "-noout"], input=key, capture_output=True, timeout=30)
    assert checked.returncode == 0, "Generated signing key is invalid"


@pytest.mark.parametrize("namespace,release", [("commons", "farmer-connector-credentials"), ("farmer", "farmer-connector")])
def test_credentials_cannot_be_installed_under_other_owners(namespace, release):
    assert render(namespace, release).returncode != 0


def test_staging_credentials_use_dedicated_secrets_and_reject_dev_namespace():
    values = ROOT / "helm/environments/staging/farmer-connector-credentials.yaml"
    def staging(namespace):
        return subprocess.run(["helm", "template", "farmer-connector-credentials", str(CHART),
                               "-n", namespace, "-f", str(values)], capture_output=True, text=True, timeout=60)
    result = staging("farmer")
    assert result.returncode == 0
    items = list(yaml.safe_load_all(result.stdout))
    assert {item["metadata"]["name"] for item in items} == {"farmer-connector-v2-staging-db", "farmer-connector-v2-staging-signing"}
    assert all(item["metadata"]["namespace"] == "farmer" for item in items)
    assert staging("far").returncode != 0
