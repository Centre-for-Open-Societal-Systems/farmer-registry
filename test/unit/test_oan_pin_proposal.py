"""The oan-helm chart-pin updater and the pull request stage, with a stand-in git and GitHub.

No network, no cluster. ci/deploy/bump_pin.py and ci/deploy/package_chart.py are standard library only because
they run on the Jenkins deploy node's stock Python; this file runs in the validation container.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
PIN = ROOT / "ci/deploy/oan-chart.json"
CHART = "openg2p-farmer-registry"


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_archive(version="1.0.0-dev.21", app="1.2.2-rc.614"):
    body = "apiVersion: v2\nname: %s\nversion: %s\nappVersion: %s\n" % (CHART, version, app)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        data = body.encode()
        info = tarfile.TarInfo(CHART + "/Chart.yaml")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


@pytest.fixture
def bump(tmp_path):
    module = load("bump_pin_under_test", "ci/deploy/bump_pin.py")
    (tmp_path / "ci/deploy").mkdir(parents=True)
    shutil.copy(PIN, tmp_path / "ci/deploy/oan-chart.json")
    shutil.copy(ROOT / "ci/deploy/oan-chart-staging.json", tmp_path / "ci/deploy/oan-chart-staging.json")
    module.PROFILE = tmp_path / "ci/deploy/oan-chart.json"
    module.ROOT = tmp_path
    return module


COMMIT = "b" * 40


class Published:
    """What oan-helm serves at one commit."""

    def __init__(self, commit=COMMIT):
        self.commit = commit
        self.files = {}

    def release(self, version, app="1.2.2-rc.614"):
        archive = fake_archive(version, app)
        name = "%s-%s.tgz" % (CHART, version)
        self.files = {
            "releases/current.yaml": ("charts:\n  farmer-registry-dashboard: 0.1.2\n  %s: %s\n" % (CHART, version)).encode(),
            "repository/" + name: archive,
            "repository/SHA256SUMS": ("%s  %s\n" % (hashlib.sha256(archive).hexdigest(), name)).encode(),
        }
        return hashlib.sha256(archive).hexdigest()

    def fetch(self, uri):
        return self.files[uri.split("/oan-helm/" + self.commit + "/")[1]]


# ---- new_pin -------------------------------------------------------------------------------------------------

def test_pin_is_rebuilt_from_the_commit(bump):
    oan = Published()
    digest = oan.release("1.0.0-dev.21", "1.2.2-rc.700")
    pin = bump.new_pin(COMMIT, fetch=oan.fetch)
    assert pin["version"] == "1.0.0-dev.21"                         # from releases/current.yaml, not the dashboard line
    assert pin["sha256"] == digest
    assert pin["platformVersion"] == "1.2.2-rc.700"                 # read from the archive
    assert pin["repository"].endswith("/oan-helm/" + COMMIT + "/repository/")
    assert bump.archive_url(pin) == pin["repository"] + CHART + "-1.0.0-dev.21.tgz"
    assert (pin["environment"], pin["namespace"], pin["release"], pin["name"]) == ("dev", "farmer", "farmer-registry", CHART)
    assert "values" not in pin                                      # dev takes its values from the live release


def test_archive_not_matching_sha256sums_is_rejected(bump):
    oan = Published()
    oan.release("1.0.0-dev.21")
    oan.files["repository/SHA256SUMS"] = ("%s  %s-1.0.0-dev.21.tgz\n" % ("0" * 64, CHART)).encode()
    with pytest.raises(ValueError, match="SHA256SUMS"):
        bump.new_pin(COMMIT, fetch=oan.fetch)


def test_version_missing_from_sha256sums_is_rejected(bump):
    oan = Published()
    oan.release("1.0.0-dev.21")
    oan.files["repository/SHA256SUMS"] = b""
    with pytest.raises(ValueError, match="not listed"):
        bump.new_pin(COMMIT, fetch=oan.fetch)


def test_archive_with_another_chart_version_is_rejected(bump):
    oan = Published()
    oan.release("1.0.0-dev.21")
    other = fake_archive(version="1.0.0-dev.20")
    oan.files["repository/%s-1.0.0-dev.21.tgz" % CHART] = other
    oan.files["repository/SHA256SUMS"] = ("%s  %s-1.0.0-dev.21.tgz\n" % (hashlib.sha256(other).hexdigest(), CHART)).encode()
    with pytest.raises(ValueError, match="expected 1.0.0-dev.21"):
        bump.new_pin(COMMIT, fetch=oan.fetch)


@pytest.mark.parametrize("bad", ["main", "abc1234", "B" * 40])
def test_branch_or_short_commit_is_rejected(bump, bad):
    with pytest.raises(ValueError):
        bump.new_pin(bad, fetch=Published().fetch)


def test_placeholder_version_is_rejected(bump):
    with pytest.raises(ValueError):
        bump.new_pin(COMMIT, version="0.0.0-develop.1", fetch=Published().fetch)


# ---- proposal ------------------------------------------------------------------------------------------------

HEAD = "c" * 40


def proposal(bump, old, oan):
    oan.commit = HEAD
    return bump.proposal(old, fetch=oan.fetch, head=lambda: HEAD)


def test_version_order(bump):
    key = bump.version_key
    assert key("1.0.0-dev.9") < key("1.0.0-dev.10")                 # numeric, not text order
    assert key("1.0.0-dev.20") < key("1.0.0-dev.21")
    assert key("1.0.0-dev.99") < key("1.0.0")
    with pytest.raises(ValueError):
        key("latest")


def test_a_newer_chart_is_proposed(bump):
    old = json.loads(bump.PROFILE.read_text())
    oan = Published()
    oan.release("1.0.0-dev.22", old["platformVersion"])
    new, why = proposal(bump, old, oan)
    assert new is not None and "newer chart 1.0.0-dev.22" in why
    assert new["repository"].endswith("/oan-helm/" + HEAD + "/repository/")


def test_the_same_chart_is_up_to_date_whatever_else_changed_on_main(bump):
    old = json.loads(bump.PROFILE.read_text())
    oan = Published()
    old["sha256"] = oan.release(old["version"], old["platformVersion"])
    new, why = proposal(bump, old, oan)                             # a new commit on main, same chart
    assert new is None and "up to date" in why


def test_an_older_chart_is_never_proposed(bump):
    old = json.loads(bump.PROFILE.read_text())
    oan = Published()
    oan.release("1.0.0-dev.18", "1.2.2-rc.600")
    with pytest.raises(ValueError, match="downgrade"):
        proposal(bump, old, oan)


def test_a_changed_archive_for_the_same_version_is_refused(bump):
    old = json.loads(bump.PROFILE.read_text())
    oan = Published()
    oan.release(old["version"], "1.2.2-rc.999")                     # different bytes, same version
    with pytest.raises(ValueError, match="immutable"):
        proposal(bump, old, oan)


def test_head_commit_is_read_with_git_ls_remote(bump):
    assert bump.head_commit(run=lambda cmd: "%s\trefs/heads/main\n" % HEAD) == HEAD
    with pytest.raises(ValueError):
        bump.head_commit(run=lambda cmd: "")


def test_only_the_dev_pin_is_rewritten_even_for_a_new_platform(bump):
    old = json.loads(bump.PROFILE.read_text())
    oan = Published()
    oan.release("1.0.0-dev.22", "1.2.2-rc.700")
    new, _ = proposal(bump, old, oan)
    assert new["platformVersion"] == "1.2.2-rc.700"
    assert bump.update_companions(old, new, root=bump.ROOT) == []
    staging = (bump.ROOT / "ci/deploy/oan-chart-staging.json").read_text()
    assert bump.apply_pin(old, new, bump.ROOT) == ["ci/deploy/oan-chart.json"]
    assert json.loads(bump.PROFILE.read_text())["version"] == "1.0.0-dev.22"
    assert (bump.ROOT / "ci/deploy/oan-chart-staging.json").read_text() == staging   # the staging pin is never touched


def test_the_pin_file_keeps_its_format(bump):
    # A pin pull request must show only the changed lines.
    old = json.loads(bump.PROFILE.read_text())
    assert json.dumps(old, indent=2) + "\n" == PIN.read_text()


def test_the_real_pin_is_a_pin_the_updater_understands():
    pin = json.loads(PIN.read_text())
    assert pin["name"] == CHART
    assert len(pin["sha256"]) == 64
    assert pin["repository"].split("/oan-helm/")[1].split("/")[0].isalnum()


# ---- the pull request stage ----------------------------------------------------------------------------------

def test_the_stage_scripts_use_only_what_the_deploy_nodes_python_has():
    # vpn-agent2 runs an old Python: no str.removesuffix, no third-party imports.
    for name in ("bump_pin.py", "package_chart.py"):
        source = (ROOT / "ci/deploy" / name).read_text()
        assert "removesuffix" not in source and "removeprefix" not in source
        for line in source.splitlines():
            if line.startswith(("import ", "from ")):
                assert line.split()[1] not in ("yaml", "requests", "pytest")
