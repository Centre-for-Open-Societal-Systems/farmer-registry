"""Fence obsolete native-candidate mutation before tools, preserving legacy paths."""
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
    paths += [f"docker/oan/{role}.Dockerfile" for role in pins.ROLES]
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    return tmp_path


@pytest.mark.parametrize("kind", ["parent-tag", "parent-repository", "platform", "mutable-archive"])
def test_release_contract_rejects_unreviewed_pin_drift(source, kind):
    if kind.startswith("parent"):
        path = source / "docker/oan/celery.Dockerfile"
        content = path.read_text()
        content = content.replace("1.2.1-rc.192", "unreviewed") if kind == "parent-tag" else content.replace("openg2p/openg2p-farmer-registry-celery", "example/other")
        path.write_text(content)
    else:
        path = source / "ci/deploy/oan-chart.json"
        value = json.loads(path.read_text())
        value["platformVersion" if kind == "platform" else "repository"] = "unreviewed" if kind == "platform" else "https://example.invalid/latest/"
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        pins.check(source)


@pytest.mark.skipif(not BASH, reason="Bash required")
@pytest.mark.parametrize("args", [[], ["-n"], ["--check", "1.2.2-rc.557"], ["1.2.2-rc.557"]])
def test_native_candidate_fenced_before_network_tools_or_mutation(source, args):
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    env = dict(os.environ, PATH="")
    result = subprocess.run([BASH, (ROOT / "scripts/bump-rp-version.sh").as_posix(), *args], cwd=source, env=env, text=True, capture_output=True, check=False)
    assert result.returncode != 0 and "Native OAN candidate" in result.stderr
    assert before == {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}


@pytest.mark.skipif(not BASH, reason="Bash required")
def test_help_is_useful_without_tools_and_nonnative_fixture_keeps_legacy_path(tmp_path):
    script = (ROOT / "scripts/bump-rp-version.sh").as_posix()
    env = dict(os.environ, PATH="")
    help_result = subprocess.run([BASH, script, "--help"], cwd=tmp_path, env=env, text=True, capture_output=True, check=False)
    assert help_result.returncode == 0 and "Native OAN candidates reject" in help_result.stdout
    legacy = subprocess.run([BASH, script, "-n"], cwd=tmp_path, env=env, text=True, capture_output=True, check=False)
    assert legacy.returncode != 0 and "curl is required" in legacy.stderr
    assert "Native OAN candidate:" not in legacy.stderr
