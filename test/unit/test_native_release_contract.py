"""The reviewed native release contract, and scripts/bump-rp-version.sh failing before it writes or reaches the network."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("native_pins", ROOT / "ci/validation/check_release_pins.py")
pins = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pins)
BASH = shutil.which("bash")


@pytest.fixture
def source(tmp_path):
    paths = ["ci/validation/native-release-contract.json", "ci/deploy/oan-chart.json"]
    paths += [f"docker/{role}/Dockerfile" for role in pins.ROLES]
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    return tmp_path


@pytest.mark.parametrize("kind", ["parent-tag", "parent-repository", "platform", "mutable-archive"])
def test_release_contract_rejects_unreviewed_pin_drift(source, kind):
    if kind.startswith("parent"):
        path = source / "docker/celery/Dockerfile"
        content = path.read_text()
        content = content.replace("1.2.2-rc.625", "unreviewed") if kind == "parent-tag" else content.replace("openg2p/openg2p-registry-celery", "example/other")
        path.write_text(content)
    else:
        path = source / "ci/deploy/oan-chart.json"
        value = json.loads(path.read_text())
        value["platformVersion" if kind == "platform" else "repository"] = "unreviewed" if kind == "platform" else "https://example.invalid/latest/"
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        pins.check(source)


def test_the_reviewed_files_pass(source):
    assert pins.check(source)["platform"] == "1.2.2-rc.625"


@pytest.mark.skipif(not BASH, reason="Bash required")
@pytest.mark.parametrize("args, message", [([], "give the platform version"), (["-n"], "give the platform version"),
                                           (["--check", "1.2.2-rc.681"], "run from the repository root"),
                                           (["1.2.2-rc.681"], "run from the repository root")])
def test_bump_fails_before_tools_network_or_writes(source, args, message):
    # The fixture has the Dockerfiles but no chart directory, and PATH is empty: no curl, helm or python3 could run.
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    env = dict(os.environ, PATH="")
    result = subprocess.run([BASH, (ROOT / "scripts/bump-rp-version.sh").as_posix(), *args], cwd=source, env=env,
                            text=True, capture_output=True, check=False)
    assert result.returncode != 0 and message in result.stderr
    assert before == {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}


@pytest.mark.skipif(not BASH, reason="Bash required")
def test_help_is_useful_without_tools_and_tools_are_checked_first(tmp_path):
    script = (ROOT / "scripts/bump-rp-version.sh").as_posix()
    env = dict(os.environ, PATH="")
    help_result = subprocess.run([BASH, script, "--help"], cwd=tmp_path, env=env, text=True, capture_output=True, check=False)
    assert help_result.returncode == 0 and "BASE_IMAGE_VERSION" in help_result.stdout and "no automatic" in help_result.stdout
    (tmp_path / "docker/staff-ui").mkdir(parents=True)
    (tmp_path / "docker/staff-ui/Dockerfile").write_text("FROM node:20-alpine\n")
    (tmp_path / "helm/openg2p-farmer-registry").mkdir(parents=True)
    missing = subprocess.run([BASH, script, "-n", "1.2.2-rc.681"], cwd=tmp_path, env=env, text=True, capture_output=True, check=False)
    assert missing.returncode != 0 and "curl, python3 and helm are required" in missing.stderr
