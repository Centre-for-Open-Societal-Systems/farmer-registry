"""Image names: eoan/farmer-registry/<image>[-<rpVersion>]:<version>-<branch>.<build>.

<version> is init.yaml's; <rpVersion> is the ARG BASE_IMAGE_VERSION default of the platform Dockerfiles."""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("image_names", ROOT / "ci/deploy/image_names.py")
image_names = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image_names)
INIT = (ROOT / "init.yaml").read_text(encoding="utf-8")
RP = re.search(r"(?m)^ARG BASE_IMAGE_VERSION=(\S+)$", (ROOT / "docker/staff-api/Dockerfile").read_text()).group(1)
VERSION = re.search(r"(?m)^version: (\S+)$", INIT).group(1)


@pytest.mark.parametrize("image", ["staff-ui", "staff-api", "partner-api", "celery", "db-seed", "sanity-tests"])
def test_only_the_platform_images_carry_the_platform_version(image):
    assert image_names.repository(image) == "eoan/farmer-registry/%s-%s" % (image, RP)


@pytest.mark.parametrize("image, repository", [("registry-connector", "eoan/farmer-registry/registry-connector-api"),
                                               ("registry-connector-ui", "eoan/farmer-registry/registry-connector-ui"),
                                               ("dashboard-api", "eoan/farmer-registry/dashboard-api"),
                                               ("dashboard-ui", "eoan/farmer-registry/dashboard-ui")])
def test_other_images_have_no_platform_suffix(image, repository):
    # The repositories created for the eoan names (19 Nov 2026); the -<rpVersion> dashboard ones are not used.
    assert image_names.repository(image) == repository
    assert image_names.is_repository(repository, image)
    assert not image_names.is_repository(repository + "-" + RP, image)


def test_init_yaml_holds_the_version_and_the_dockerfiles_the_platform():
    assert image_names.read_init() == {"version": VERSION}
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)
    assert image_names.platform_version() == RP
    assert re.fullmatch(r"[0-9a-f]{40}", image_names.platform_commit())


@pytest.mark.parametrize("text, problem", [
    ("", "version"),
    ("version: 1.0.0-develop.3\n", "version"),
    ("version: 1.0.0\nrpVersion: 1.2.2-rc.625\n", "rpVersion"),
    ("version: 1.0.0\nchannel: develop\n", "channel"),
    ("version: 1.0.0\nversion: 1.0.1\n", "version")])
def test_a_bad_init_yaml_is_refused(tmp_path, text, problem):
    (tmp_path / "init.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=problem):
        image_names.read_init(tmp_path / "init.yaml")


def test_repository_carries_the_platform_version_of_the_chart():
    assert image_names.repository("staff-ui") == "eoan/farmer-registry/staff-ui-" + RP


def test_tag_is_the_chart_version_branch_and_build_number():
    assert image_names.tag("develop", 300) == VERSION + "-develop.300"


@pytest.mark.parametrize("branch, expected", [("PR-42", "pr-42"), ("feature/New_Field", "feature-new-field")])
def test_tag_turns_any_branch_into_a_docker_tag(branch, expected):
    assert image_names.tag(branch, "7") == "%s-%s.7" % (VERSION, expected)


@pytest.mark.parametrize("branch, build", [("develop", "0"), ("develop", ""), ("develop", "3a"), ("//", "5")])
def test_tag_refuses_a_missing_branch_or_build_number(branch, build):
    with pytest.raises(ValueError):
        image_names.tag(branch, build)


@pytest.mark.parametrize("value, valid", [("0.0.0-develop.300", True), ("1.0.0-pr-42.3", True),
                                          ("abcdef012345", False), ("0.0.0.develop.300", False),
                                          ("0.0.0-develop.0", False), ("0.0.0-develop", False)])
def test_is_tag(value, valid):
    assert image_names.is_tag(value) is valid


def test_installed_releases_may_still_run_the_openg2p_images():
    assert image_names.legacy_repository("celery") == "openg2p/farmer-registry/celery"


def test_command_line(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["image_names.py", "tag", "develop", "12"])
    image_names.main()
    monkeypatch.setattr("sys.argv", ["image_names.py", "repository", "db-seed"])
    image_names.main()
    assert capsys.readouterr().out.splitlines() == [VERSION + "-develop.12", "eoan/farmer-registry/db-seed-" + RP]


@pytest.mark.parametrize("value, valid", [
    ("eoan/farmer-registry/celery-" + "1.2.2-rc.625", True),
    ("eoan/farmer-registry/celery-1.2.2-rc.614", True),          # an earlier platform: the image of an installed release
    ("openg2p/farmer-registry/celery", True),                     # the names before eoan
    ("eoan/farmer-registry/celery", False), ("eoan/farmer-registry/staff-api-1.2.2", False),
    ("openg2p/another/celery", False), ("eoan/farmer-registry/celery-x/y", False)])
def test_is_repository(value, valid):
    assert image_names.is_repository(value, "celery") is valid


HOST = "123456789012.dkr.ecr.ap-south-1.amazonaws.com"
DIGEST = "@sha256:" + "a" * 64
COMMIT = "abcdef012345" + "b" * 28


@pytest.mark.parametrize("image, valid", [
    (HOST + "/eoan/farmer-registry/celery-" + RP + ":0.0.0-develop.300" + DIGEST, True),
    (HOST + "/openg2p/farmer-registry/celery:abcdef012345" + DIGEST, True),            # before eoan: commit12 tag
    (HOST + "/openg2p/farmer-registry/celery:0123456789ab" + DIGEST, False),           # another commit's image
    (HOST + "/eoan/farmer-registry/celery-" + RP + ":0.0.0-develop.300", False),        # no digest
    (HOST + "/eoan/farmer-registry/celery-" + RP + ":latest" + DIGEST, False),
    (HOST + "/eoan/farmer-registry/staff-api-" + RP + ":0.0.0-develop.300" + DIGEST, False),
    ("docker.io/eoan/farmer-registry/celery-" + RP + ":0.0.0-develop.300" + DIGEST, False)])
def test_is_pinned_image(image, valid):
    assert image_names.is_pinned_image(image, "celery", COMMIT) is valid


def test_is_pinned_image_without_a_commit_takes_any_commit12_tag_of_the_old_names():
    assert image_names.is_pinned_image(HOST + "/openg2p/farmer-registry/celery:0123456789ab" + DIGEST, "celery")
