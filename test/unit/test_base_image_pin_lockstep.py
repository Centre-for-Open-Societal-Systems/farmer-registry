"""Guard: init.yaml is the one place the openg2p-registry platform is chosen, and every copy agrees with it.

A variant extends ONE registry-platform version, used three ways:
  * the Docker images — every docker/*/Dockerfile built FROM a platform image declares `ARG BASE_IMAGE_VERSION` with
    no default; ci/build/images.sh and .github/workflows/build.yml pass rpVersion of init.yaml (the staff UI gets
    rpCommit, the registry-platform commit of openg2p/openg2p-registry-staff-ui:<rpVersion>)
  * the Helm chart — `appVersion` and the `openg2p-registry` dependency `version:` in Chart.yaml (Chart.yaml stays
    literal; scripts/bump-rp-version.sh writes init.yaml and Chart.yaml together)
  * the reviewed contracts — ci/validation/native-release-contract.json and ci/deploy/oan-chart.json

If these drift, the images are built FROM one base while the chart deploys another, and the overlay lands on a
harness it does not match. This test fails the build if anything ever splits them.

No dependencies beyond the stdlib + pytest — runs anywhere the other tests do.
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
INIT = image_names.read_init()


def _platform_dockerfiles():
    files = [f for f in sorted((REPO / "docker").glob("*/Dockerfile")) if PLATFORM_IMAGE.search(f.read_text())]
    return files + [REPO / "docker/staff-ui/Dockerfile"]


def _chart_pin():
    m = re.search(r"-\s*name:\s*openg2p-registry\b.*?version:\s*(\S+)", CHART.read_text(), re.S)
    return m.group(1) if m else None


def test_dockerfiles_take_the_platform_from_the_build_and_have_no_default():
    files = _platform_dockerfiles()
    assert sorted(f.parent.name for f in files) == sorted(image_names.PLATFORM_IMAGES)
    for f in files:
        declared = re.findall(r"^ARG BASE_IMAGE_VERSION(\S*)\s*$", f.read_text(), re.M)
        assert declared == [""], f"{f.relative_to(REPO)} must declare ARG BASE_IMAGE_VERSION without a default"


def test_every_copy_of_the_platform_version_is_init_yaml():
    copies = {
        "Chart.yaml appVersion": re.search(r"(?m)^appVersion:\s*(\S+)", CHART.read_text()).group(1),
        "Chart.yaml openg2p-registry dependency": _chart_pin(),
        "ci/deploy/oan-chart.json platformVersion": json.loads((REPO / "ci/deploy/oan-chart.json").read_text())["platformVersion"],
        "ci/validation/native-release-contract.json platformVersion":
            json.loads((REPO / "ci/validation/native-release-contract.json").read_text())["platformVersion"],
    }
    split = {name: value for name, value in copies.items() if value != INIT["rpVersion"]}
    if split:
        pytest.fail("init.yaml rpVersion is %s, but:\n%s\n\nChange the platform with scripts/bump-rp-version.sh"
                    % (INIT["rpVersion"], "\n".join("  %s: %s" % item for item in split.items())))


def test_chart_dependency_lock_matches_the_pinned_platform():
    lock = CHART.with_name("Chart.lock")
    assert lock.is_file(), "Pinned Farmer chart must commit its dependency lock"
    assert re.search(r"version:\s*" + re.escape(INIT["rpVersion"]) + r"\s", lock.read_text())
    assert "https://openg2p.github.io/openg2p-helm" in lock.read_text()


def test_builds_pass_init_yaml_to_every_platform_image():
    images = (REPO / "ci/build/images.sh").read_text()
    assert 'rp_version=$(python3 ci/deploy/image_names.py field rpVersion)' in images
    assert 'rp_commit=$(python3 ci/deploy/image_names.py field rpCommit)' in images
    assert 'python3 ci/build/check_rp_commit.py "$rp_version" "$rp_commit"' in images
    builds = re.findall(r"docker build (.*?)-t \"oan-ci/([a-z$-]+)", images.replace("\\\n", " "))
    arguments = {name: line for line, name in builds}
    assert "for component in staff-api partner-api celery db-seed; do" in images
    assert '--build-arg "BASE_IMAGE_VERSION=$rp_version"' in arguments["$component"]
    assert '--build-arg "BASE_IMAGE_VERSION=$rp_version"' in arguments["sanity-tests"]
    assert '--build-arg "BASE_IMAGE_VERSION=$rp_commit"' in arguments["staff-ui"]
    workflow = (REPO / ".github/workflows/build.yml").read_text()
    assert "BASE_IMAGE_VERSION=${{ matrix.component == 'staff-ui' && steps.platform.outputs.commit" \
           " || steps.platform.outputs.version }}" in workflow


def test_image_parents_and_central_platform_source_contract():
    path = REPO / "ci/validation/check_release_pins.py"
    spec = importlib.util.spec_from_file_location("release_pins", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.check(REPO)
    assert result["image_parent"] == result["platform"] == INIT["rpVersion"]
