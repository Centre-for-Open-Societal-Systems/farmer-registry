"""Render the deployed dashboard chart, including its lifecycle hooks."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "helm/farmer-registry-dashboard"
VALUES = ROOT / "helm/environments/dev/services/farmer-registry-dashboard.yaml"
REPOSITORY = "123456789012.dkr.ecr.ap-south-1.amazonaws.com/oan/farmer-registry/dashboard-ui"
pytestmark = pytest.mark.skipif(not shutil.which("helm"), reason="Helm required")


def mappings(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from mappings(child)


@pytest.mark.parametrize("tag,version", [
    ("042d0f4c271d@sha256:" + "a" * 64, "042d0f4c271d"),
    ("042d0f4c271d", "042d0f4c271d"),
    ("a" * 128, "a" * 63),
    ("_release.-", "release"),
    ("a" * 62 + "-tail", "a" * 62),
])
def test_digest_pinned_images_have_valid_labels_on_resources_and_hooks(tag, version):
    rendered = subprocess.run([
        "helm", "template", "farmer-registry-dashboard", str(CHART),
        "-n", "farmer", "-f", str(VALUES),
        "--set-string", "image.repository=" + REPOSITORY,
        "--set-string", "image.tag=" + tag,
    ], check=True, capture_output=True, text=True).stdout
    documents = [d for d in yaml.safe_load_all(rendered) if d]
    hooks = [d for d in documents if "helm.sh/hook" in d["metadata"].get("annotations", {})]
    assert {d["kind"] for d in hooks} == {"ServiceAccount", "Role", "RoleBinding", "Job"}
    assert any(d["kind"] == "Deployment" for d in documents)
    versions, images = [], []
    for document in documents:
        for node in mappings(document):
            for key, value in node.get("metadata", {}).get("labels", {}).items():
                assert isinstance(value, str), (document["kind"], key, value)
                assert len(value) <= 63, (document["kind"], key, value)
                assert re.fullmatch(r"(?:[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?)?", value), (key, value)
                if key == "app.kubernetes.io/version":
                    versions.append(value)
            if node.get("image", "").startswith(REPOSITORY + ":"):
                images.append(node["image"])
    assert versions and set(versions) == {version}
    # Deployment, IAM setup and authenticated chart smoke must all retain the
    # complete immutable image reference, even though labels omit its digest.
    assert len(images) == 3
    assert set(images) == {REPOSITORY + ":" + tag}
