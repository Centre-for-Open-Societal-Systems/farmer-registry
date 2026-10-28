"""Guard: the openg2p-registry pin must be identical in every place it appears.

A variant extends ONE registry-platform version, used two ways:
  * the Docker base images — `ARG BASE_IMAGE_VERSION=<v>` in every docker/*/Dockerfile
    whose FROM is a platform image (`openg2p/openg2p-registry-<role>`); the farmer
    parents (`openg2p/openg2p-farmer-registry-<role>`) carry their own pin, reviewed
    by ci/validation/check_release_pins.py
  * the Helm chart — the `openg2p-registry` dependency `version:` in Chart.yaml

If these drift, the sanity image is built FROM one base while the chart deploys
another, and the overlay lands on a harness it does not match (the failure that
bit us repeatedly). The legacy bump mutator is fenced on native OAN candidates; this test
fails the build if anything ever splits them again.

No dependencies beyond the stdlib + pytest — runs anywhere the other tests do.
"""

import pathlib
import json
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
CHART = REPO / "helm" / "openg2p-farmer-registry" / "Chart.yaml"


PLATFORM_IMAGE = re.compile(r"^FROM openg2p/openg2p-registry-[a-z-]+:\$\{BASE_IMAGE_VERSION\}$", re.M)


def _docker_pins():
    pins = {}
    for f in sorted((REPO / "docker").glob("*/Dockerfile")):
        content = f.read_text()
        m = re.search(r"^ARG BASE_IMAGE_VERSION=(\S+)", content, re.M)
        if m and PLATFORM_IMAGE.search(content):
            pins[f.relative_to(REPO).as_posix()] = m.group(1)
    return pins


def _chart_pin():
    m = re.search(
        r"-\s*name:\s*openg2p-registry\b.*?version:\s*(\S+)",
        CHART.read_text(), re.S,
    )
    return m.group(1) if m else None


def test_platform_pin_is_in_lockstep():
    docker = _docker_pins()
    chart = _chart_pin()
    assert docker, "no ARG BASE_IMAGE_VERSION found in any docker/*/Dockerfile built FROM a platform image"
    assert chart, "no openg2p-registry dependency version found in Chart.yaml"

    oan_pin = json.loads((REPO / 'ci/deploy/oan-chart.json').read_text())['platformVersion']
    all_pins = set(docker.values()) | {chart, oan_pin}
    if len(all_pins) != 1:
        lines = [f"  Chart.yaml openg2p-registry dependency: {chart}"]
        lines += [f"  {p}: {v}" for p, v in docker.items()]
        pytest.fail(
            "openg2p-registry pin has SPLIT — images and chart must be identical:\n"
            + "\n".join(lines)
            + "\n\nReview ci/validation/native-release-contract.json and the immutable central chart profile; legacy bump is disabled on native OAN candidates"
        )


def test_chart_dependency_lock_matches_the_pinned_platform():
    lock = CHART.with_name("Chart.lock")
    assert lock.is_file(), "Pinned Farmer chart must commit its dependency lock"
    assert re.search(r"version:\s*" + re.escape(_chart_pin()) + r"\s", lock.read_text())
    assert "https://openg2p.github.io/openg2p-helm" in lock.read_text()


def test_native_farmer_parent_and_central_platform_source_contract():
    import importlib.util
    path = REPO / "ci/validation/check_release_pins.py"
    spec = importlib.util.spec_from_file_location("release_pins", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.check(REPO)
    assert result["numeric_version_equality_required"] is False
