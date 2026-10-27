"""A source merge can publish images without selecting any cluster writer."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


delivery = module("delivery", "ci/delivery.py")
worker = module("worker_probe", "ci/validation/check_native_worker_save.py")
ECR = "123456789012.dkr.ecr.ap-south-1.amazonaws.com"
COMMIT = "abcdef012345" + "b" * 28
COMPONENTS = ("staff-api", "partner-api", "celery", "db-seed", "sanity-tests", "staff-ui")


@pytest.mark.parametrize("environment", [{}, {"NEW_DEV_DELIVERY_ACTION": ""}, {"NEW_DEV_DELIVERY_ACTION": "publish-only"}])
def test_first_build_or_explicit_publication_never_selects_deployment(environment):
    assert delivery.action(environment) == "publish-only"


@pytest.mark.parametrize("reset", ["check", "initialize", "resume"])
def test_explicit_deploy_preserves_existing_reset_gate_selection(reset):
    assert delivery.action({"NEW_DEV_DELIVERY_ACTION": "deploy", "NEW_DEV_RESET_ACTION": reset}) == "deploy"


@pytest.mark.parametrize("environment", [
    {"NEW_DEV_DELIVERY_ACTION": "automatic"},
    {"NEW_DEV_DELIVERY_ACTION": "Deploy"},
    {"NEW_DEV_RESET_ACTION": "initialize"},
    {"NEW_DEV_DELIVERY_ACTION": "publish-only", "NEW_DEV_RESET_ACTION": "resume"},
    {"NEW_DEV_DELIVERY_ACTION": "deploy", "NEW_DEV_RESET_ACTION": "automatic"},
])
def test_ambiguous_actions_and_resets_during_publication_are_rejected(environment):
    with pytest.raises(ValueError):
        delivery.action(environment)


@pytest.fixture
def published(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "service-outcomes/registry-images.tsv"
    path.parent.mkdir()
    path.write_text("".join(f"{component}\t{ECR}/openg2p/farmer-registry/{component}:{COMMIT[:12]}\tsha256:{'c' * 64}\n"
                            for component in COMPONENTS), encoding="utf-8")
    return {"ECR_REGISTRY": ECR, "IMAGE_TAG": COMMIT[:12], "SOURCE_COMMIT": COMMIT,
            "OAN_DELIVERY_ACTION": "publish-only"}, path


def test_publication_receipt_records_all_digests_and_no_deployment_claim(published):
    environment, _ = published
    result = delivery.publication(environment)
    assert result["sourceCommit"] == COMMIT
    assert set(result["images"]) == set(COMPONENTS)
    assert result["verification"] == "immutable-images-published"
    assert result["deployment"] == "not-attempted-by-publication"
    assert result["acceptance"] == "pending-live-application-checks"
    assert "cluster" not in json.dumps(result)


@pytest.mark.parametrize("defect", ["missing", "duplicate", "digest", "repository", "source", "action"])
def test_receipt_rejects_incomplete_or_mismatched_build_provenance(published, defect):
    environment, path = published
    content = path.read_text()
    if defect == "missing":
        content = "\n".join(content.splitlines()[:-1])
    elif defect == "duplicate":
        content += content.splitlines()[0] + "\n"
    elif defect == "digest":
        content = content.replace("sha256:", "unverified:")
    elif defect == "repository":
        content = content.replace("/openg2p/farmer-registry/", "/openg2p/another/")
    elif defect == "source":
        environment["SOURCE_COMMIT"] = "d" * 40
    else:
        environment["NEW_DEV_DELIVERY_ACTION"] = "deploy"
    path.write_text(content)
    with pytest.raises(ValueError):
        delivery.publication(environment)


def test_every_cluster_or_optional_stage_requires_explicit_deploy():
    pipeline = (ROOT / "ci/pipelines/dev.groovy").read_text()
    for stage in ("Deploy new dev", "Build optional services", "Deploy optional services"):
        definition = pipeline.split("stage('" + stage + "')", 1)[1].split("steps {", 1)[0]
        assert "env.OAN_DELIVERY_ACTION == 'deploy'" in definition
        assert "branch 'develop'" in definition
        assert "not { changeRequest() }" in definition
    publication = pipeline.split("stage('Publish dev images')", 1)[1].split("steps {", 1)[0]
    assert "branch 'develop'" in publication and "not { changeRequest() }" in publication
    assert "OAN_DELIVERY_ACTION" not in publication
    assert "COORDINATE_SERVICES', defaultValue: false" in pipeline
    assert "ci-output/native-worker-save/**" in pipeline
    assert "check_native_worker_save.py" in (ROOT / "ci/build/images.sh").read_text()
    preserving = pipeline.split("stage('Preserving Farmer adoption')",1)[1].split("steps {",1)[0]
    assert "env.OAN_DELIVERY_ACTION in ['preserve-preflight', 'preserve-upgrade']" in preserving
    assert "branch 'develop'" in preserving and "not { changeRequest() }" in preserving


@pytest.mark.parametrize('action',['preserve-preflight','preserve-upgrade'])
def test_preserving_modes_cannot_request_a_reset(action):
    assert delivery.action({'NEW_DEV_DELIVERY_ACTION':action})==action
    for reset in ('initialize','resume'):
        with pytest.raises(ValueError):
            delivery.action({'NEW_DEV_DELIVERY_ACTION':action,'NEW_DEV_RESET_ACTION':reset})


JENKINS = {"JENKINS_URL": "https://jenkins.oanstaging.com/", "JOB_NAME": "Gen2-Package/farmer-registry/develop",
           "BRANCH_NAME": "develop", "BUILD_NUMBER": "30"}


def test_native_worker_probe_accepts_existing_hosted_ci_and_jenkins_only():
    assert worker.permitted_ci("linux", {"GITHUB_ACTIONS": "true"})
    assert worker.permitted_ci("linux", JENKINS)
    assert not worker.permitted_ci("win32", JENKINS)
    assert not worker.permitted_ci("linux", {})


@pytest.mark.parametrize("key,value", [
    ("JENKINS_URL", ""), ("JOB_NAME", "another/job"), ("BRANCH_NAME", "staging"),
    ("BUILD_NUMBER", ""), ("BUILD_NUMBER", "latest"), ("CHANGE_ID", "124"),
])
def test_native_worker_probe_rejects_other_jobs_and_local_fallback(key, value):
    assert not worker.permitted_ci("linux", {**JENKINS, key: value})
