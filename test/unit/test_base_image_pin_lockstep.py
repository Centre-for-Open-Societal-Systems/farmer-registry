"""Guard: the openg2p-registry platform pin is identical in every place it appears.

As in OpenG2P (farmer-registry test/test_rp_pin_lockstep.py), the pin is the `ARG BASE_IMAGE_VERSION=<v>` default
of every docker/*/Dockerfile built FROM a platform image: a Dockerfile cannot read the version from another file
before FROM, and a plain `docker build -f docker/<role>/Dockerfile .` must build without arguments. The same version
is also
  * the Helm chart's `appVersion` and `openg2p-registry` dependency `version:` in Chart.yaml (and Chart.lock)
  * the reviewed contracts — ci/validation/native-release-contract.json and ci/deploy/oan-chart.json
  * the -<rpVersion> of the platform images' ECR repositories (ci/deploy/image_names.py reads it from the Dockerfiles)
and the staff UI Dockerfile's default is the registry-platform commit of that version's staff UI image
(ci/build/check_rp_commit.py checks it against the image label).

If these drift, the images are built FROM one base while the chart deploys another. scripts/bump-rp-version.sh
changes them together; this test fails the build if anything ever splits them.
"""

import importlib.util
import json
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
CHART = REPO / "helm" / "openg2p-farmer-registry" / "Chart.yaml"
PLATFORM_IMAGE = re.compile(r"^FROM openg2p/openg2p-registry-[a-z-]+:\$\{BASE_IMAGE_VERSION\}$", re.M)

spec = importlib.util.spec_from_file_location("image_names", REPO / "ci/deploy/image_names.py")
image_names = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image_names)


def _docker_pins():
    pins = {}
    for f in sorted((REPO / "docker").glob("*/Dockerfile")):
        content = f.read_text()
        m = re.search(r"^ARG BASE_IMAGE_VERSION=(\S+)", content, re.M)
        if m and PLATFORM_IMAGE.search(content):
            pins[f.relative_to(REPO).as_posix()] = m.group(1)
    return pins


def _chart_pin():
    m = re.search(r"-\s*name:\s*openg2p-registry\b.*?version:\s*(\S+)", CHART.read_text(), re.S)
    return m.group(1) if m else None


def test_every_platform_dockerfile_declares_the_pin():
    assert sorted(pathlib.PurePosixPath(p).parent.name for p in _docker_pins()) == sorted(image_names.PLATFORM_DOCKERFILES)


def test_platform_pin_is_in_lockstep():
    docker = _docker_pins()
    copies = dict(docker)
    copies["Chart.yaml appVersion"] = re.search(r"(?m)^appVersion:\s*(\S+)", CHART.read_text()).group(1)
    copies["Chart.yaml openg2p-registry dependency"] = _chart_pin()
    copies["ci/deploy/oan-chart.json"] = json.loads((REPO / "ci/deploy/oan-chart.json").read_text())["platformVersion"]
    copies["ci/validation/native-release-contract.json"] = \
        json.loads((REPO / "ci/validation/native-release-contract.json").read_text())["platformVersion"]
    if len(set(copies.values())) != 1:
        pytest.fail("openg2p-registry pin has SPLIT — images and chart must be identical:\n"
                    + "\n".join("  %s: %s" % item for item in copies.items())
                    + "\n\nChange the platform with scripts/bump-rp-version.sh <version>")
    assert image_names.platform_version() == set(copies.values()).pop()


def test_staff_ui_is_rebuilt_from_a_registry_platform_commit():
    assert re.fullmatch(r"[0-9a-f]{40}", image_names.platform_commit())
    assert ("openg2p/openg2p-registry-staff-ui:%s." % image_names.platform_version()) in \
        (REPO / "docker/staff-ui/Dockerfile").read_text()


def test_chart_dependency_lock_matches_the_pinned_platform():
    lock = CHART.with_name("Chart.lock")
    assert lock.is_file(), "Pinned Farmer chart must commit its dependency lock"
    assert re.search(r"version:\s*" + re.escape(_chart_pin()) + r"\s", lock.read_text())
    assert "https://openg2p.github.io/openg2p-helm" in lock.read_text()


def test_no_build_overrides_the_dockerfile_pin():
    # The Dockerfile default is what is built: a --build-arg would let the build and the reviewed pin differ.
    for path in ("ci/build/images.sh", ".github/workflows/build.yml", ".github/workflows/checks.yml"):
        assert "BASE_IMAGE_VERSION=" not in (REPO / path).read_text(), path
    images = (REPO / "ci/build/images.sh").read_text()
    assert "ci/build/check_rp_commit.py" in images and "image_names.py platform-commit" in images


def test_platform_dockerfiles_that_differ_are_refused(tmp_path):
    for role in image_names.PLATFORM_DOCKERFILES + ("staff-ui",):
        (tmp_path / role).mkdir()
        (tmp_path / role / "Dockerfile").write_text((REPO / "docker" / role / "Dockerfile").read_text())
    celery = tmp_path / "celery/Dockerfile"
    celery.write_text(re.sub(r"(?m)^ARG BASE_IMAGE_VERSION=\S+", "ARG BASE_IMAGE_VERSION=1.2.2-rc.681", celery.read_text()))
    with pytest.raises(ValueError, match="differ"):
        image_names.platform_version(tmp_path)


def test_image_parents_and_central_platform_source_contract():
    path = REPO / "ci/validation/check_release_pins.py"
    spec = importlib.util.spec_from_file_location("release_pins", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.check(REPO)
    assert result["image_parent"] == result["platform"] == image_names.platform_version()
