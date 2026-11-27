"""Guard: OpenG2P's Farmer extension is a pinned dependency, not a copy kept inside the OAN package.

The OAN layer is its own distribution, openg2p-registry-oan-farmer-extension (import name
openg2p_registry_oan_farmer_extension). It depends on OpenG2P's openg2p-registry-farmer-extension, which each Python
image builds as a wheel from one full upstream commit, the one farmer-extension/pyproject.toml records under
[tool.oan.upstream-farmer-extension]. The upstream extension still reports version 1.0.3 on later commits (1.2 too),
so the commit, not the version, identifies it.

sample-farmer-extension/ is OpenG2P's published extension at that commit, unchanged: its git tree is the upstream
commit's farmer-extension/ tree, so the tests that read upstream source without a platform image read it there.
"""

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXTENSION = ROOT / "farmer-extension"
OAN_PACKAGE = "openg2p_registry_oan_farmer_extension"
UPSTREAM_PACKAGE = "openg2p_registry_farmer_extension"
PYTHON_IMAGES = ("staff-api", "partner-api", "celery")


def project():
    return tomllib.loads((EXTENSION / "pyproject.toml").read_text(encoding="utf-8"))


def upstream_pin():
    return project()["tool"]["oan"]["upstream-farmer-extension"]


def dockerfile(role):
    return (ROOT / "docker" / role / "Dockerfile").read_text(encoding="utf-8")


def test_the_oan_layer_is_its_own_distribution():
    meta = project()
    assert meta["project"]["name"] == "openg2p-registry-oan-farmer-extension"
    assert meta["tool"]["hatch"]["version"]["path"] == f"src/{OAN_PACKAGE}/__init__.py"
    assert meta["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [f"src/{OAN_PACKAGE}"]


def test_the_oan_layer_depends_on_the_upstream_distribution():
    assert "openg2p-registry-farmer-extension ==1.0.3" in project()["project"]["dependencies"]


def test_the_upstream_pin_is_a_full_commit_of_openg2ps_repository():
    pin = upstream_pin()
    assert pin["repository"] == "https://github.com/OpenG2P/farmer-registry.git"
    assert re.fullmatch(r"[0-9a-f]{40}", pin["commit"]), pin["commit"]
    assert pin["subdirectory"] == "farmer-extension"
    assert re.fullmatch(r"[0-9a-f]{40}", pin["tree"]), pin["tree"]


def test_no_copy_of_the_upstream_extension_is_kept_in_the_oan_package():
    source = EXTENSION / "src"
    assert sorted(p.name for p in source.iterdir() if p.is_dir() and p.name != "__pycache__") == [OAN_PACKAGE]
    assert not list(source.rglob("openg2p_farmer"))


@pytest.mark.parametrize("role", PYTHON_IMAGES)
def test_each_python_image_selects_the_oan_package(role):
    content = dockerfile(role)
    assert re.findall(r"^ENV REGISTRY_EXTENSION_MODULE=(\S+)$", content, re.M) == [OAN_PACKAGE]


@pytest.mark.parametrize("role", PYTHON_IMAGES)
def test_each_python_image_builds_the_pinned_upstream_wheel_before_the_oan_layer(role):
    content = dockerfile(role)
    pin = upstream_pin()
    assert re.findall(r"^ARG UPSTREAM_FARMER_EXTENSION_REPOSITORY=(\S+)$", content, re.M) == [pin["repository"]]
    assert re.findall(r"^ARG UPSTREAM_FARMER_EXTENSION_COMMIT=(\S+)$", content, re.M) == [pin["commit"]]
    # The fetched tree is the pinned commit, built as a wheel from its farmer-extension/ subdirectory.
    assert 'test "$(git rev-parse HEAD)" = "${UPSTREAM_FARMER_EXTENSION_COMMIT}"' in content
    assert "pip wheel --no-deps --no-cache-dir --wheel-dir /tmp/upstream-wheel /tmp/upstream/farmer-extension" in content
    upstream = content.index("pip install --no-cache-dir /tmp/upstream-wheel/")
    oan = content.index("pip install --no-cache-dir /app/farmer-extension")
    assert upstream < oan


def test_the_db_seed_image_takes_the_oan_packages_seed():
    content = dockerfile("db-seed")
    copied = re.findall(r"^COPY farmer-extension/src/(\w+)/", content, re.M)
    assert copied and set(copied) == {OAN_PACKAGE}


@pytest.mark.skipif(not shutil.which("git") or not (ROOT / ".git").exists(), reason="needs the git checkout")
def test_sample_farmer_extension_is_the_pinned_upstream_tree_unchanged():
    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout
    assert git("status", "--porcelain", "--", "sample-farmer-extension") == ""
    assert git("rev-parse", "HEAD:sample-farmer-extension").strip() == upstream_pin()["tree"]
