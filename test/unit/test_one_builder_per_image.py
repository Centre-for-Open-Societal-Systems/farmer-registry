"""Every image repository has one builder: the Publish stage or ci/services/coordinator.py, never both.

Both push with the build's tag, and eoan repositories have immutable tags, so a repository both push to refuses the
second push. Develop build 213 failed that way (command-failed-docker-push on registry-connector-api).
"""
import importlib.util
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


image_names = load("image_names", "ci/deploy/image_names.py")
sys.path.insert(0, str(ROOT / "ci/services"))


def publish_components():
    text = (ROOT / "ci/pipelines/dev.groovy").read_text(encoding="utf-8")
    (line,) = re.findall(r"for component in ([a-z0-9 -]+); do", text)
    return line.split()


def publish_repositories():
    return {image_names.repository(component) for component in publish_components()}


def coordinator_repositories():
    coordinator = load("coordinator", "ci/services/coordinator.py")
    catalogue = yaml.safe_load((ROOT / "ci/services/catalogue.yaml").read_text(encoding="utf-8"))
    repositories = set()
    for component in catalogue["oanAddons"]["components"]:
        roles = component.get("images")
        suffixes = ["-" + role for role in roles] if roles else [""]
        repositories |= {coordinator.image_repository(component, suffix) for suffix in suffixes}
    return repositories


def test_publish_and_coordinator_never_share_a_repository():
    assert publish_repositories().isdisjoint(coordinator_repositories())


def test_the_connector_images_have_the_coordinator_as_their_builder():
    coordinator = coordinator_repositories()
    for repository in ("eoan/farmer-registry/registry-connector-api", "eoan/farmer-registry/registry-connector-ui"):
        assert repository in coordinator
        assert repository not in publish_repositories()


def test_publish_pushes_the_registry_images():
    assert set(publish_components()) == set(image_names.PLATFORM_IMAGES)
