"""Guard: the openg2p-registry pin must be identical in every place it appears.

A variant extends ONE registry-platform version, used two ways:
  * the Docker base images — `ARG RP_VERSION=<v>` in every docker/*/Dockerfile
  * the Helm chart — the `openg2p-registry` dependency `version:` in Chart.yaml

If these drift, the sanity image is built FROM one base while the chart deploys
another, and the overlay lands on a harness it does not match (the failure that
bit us repeatedly). `scripts/bump-rp-version.sh` moves them together; this test
fails the build if anything ever splits them again.

No dependencies beyond the stdlib + pytest — runs anywhere the other tests do.
"""

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
CHART = REPO / "helm" / "openg2p-farmer-registry" / "Chart.yaml"


def _docker_pins():
    pins = {}
    for f in [REPO / "Dockerfile", *sorted((REPO / "docker").glob("*/Dockerfile"))]:
        m = re.search(r"^ARG RP_VERSION=(\S+)", f.read_text(), re.M)
        if m:
            pins[f.relative_to(REPO).as_posix()] = m.group(1)
    return pins


def _chart_pin():
    m = re.search(
        r"-\s*name:\s*openg2p-registry\b.*?version:\s*(\S+)",
        CHART.read_text(), re.S,
    )
    return m.group(1) if m else None


def test_rp_pin_is_in_lockstep():
    docker = _docker_pins()
    chart = _chart_pin()
    assert docker, "no ARG RP_VERSION found in any docker/*/Dockerfile"
    assert chart, "no openg2p-registry dependency version found in Chart.yaml"

    jenkins = re.search(r'^\s*RP_VERSION\s*=\s*["\']([^"\']+)',
                        (REPO / "Jenkinsfile").read_text(), re.M)
    assert jenkins, "no RP_VERSION pin found in Jenkinsfile"
    all_pins = set(docker.values()) | {chart, jenkins.group(1)}
    if len(all_pins) != 1:
        lines = [f"  Chart.yaml openg2p-registry dependency: {chart}"]
        lines += [f"  {p}: {v}" for p, v in docker.items()]
        lines.append(f"  Jenkinsfile: {jenkins.group(1)}")
        pytest.fail(
            "openg2p-registry pin has SPLIT — images and chart must be identical:\n"
            + "\n".join(lines)
            + "\n\nFix with: ./scripts/bump-rp-version.sh <version>"
        )


def test_staff_ui_pin_matches_platform():
    """The unified build is what both Jenkins and local Compose actually ship."""
    pins = []
    for f in (REPO / "Dockerfile", REPO / "docker" / "staff-ui" / "Dockerfile"):
        match = re.search(r"^ARG STAFF_UI_VERSION=(\S+)", f.read_text(), re.M)
        assert match, f"missing STAFF_UI_VERSION in {f.relative_to(REPO)}"
        pins.append(match.group(1))
    assert set(pins) == {_chart_pin()}, "staff UI and registry platform pins have split"
