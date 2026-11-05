"""Every develop build publishes the images and deploys them; fresh-install stays a deliberate choice."""
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


@pytest.mark.parametrize("environment", [{}, {"DELIVERY_ACTION": ""}, {"DELIVERY_ACTION": "publish-only"}])
def test_first_build_or_a_stale_parameter_definition_deploys(environment):
    # A branch-index build has no parameter yet, and a build started before the button was removed still
    # offers the retired publish-only choice: both mean the default, deploy.
    assert delivery.action(environment) == "deploy"


@pytest.mark.parametrize("selected", ["deploy", "fresh-install"])
def test_delivery_actions_are_the_two_choices(selected):
    assert delivery.action({"DELIVERY_ACTION": selected}) == selected
    assert delivery.ACTIONS == ("deploy", "fresh-install")


@pytest.mark.parametrize("environment", [
    {"DELIVERY_ACTION": "automatic"},
    {"DELIVERY_ACTION": "Deploy"},
    {"DELIVERY_ACTION": "preserve-upgrade"},
    {"DELIVERY_ACTION": "reset"},
])
def test_unknown_actions_are_rejected(environment):
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
            "DELIVERY_ACTION": "deploy"}, path


def test_publication_receipt_records_all_digests_and_no_deployment_claim(published):
    environment, _ = published
    result = delivery.publication(environment)
    assert result["sourceCommit"] == COMMIT
    assert set(result["images"]) == set(COMPONENTS)
    assert result["verification"] == "immutable-images-published"
    assert result["deployment"] == "not-attempted-by-publication"
    assert result["acceptance"] == "pending-live-application-checks"
    assert "cluster" not in json.dumps(result)


@pytest.mark.parametrize("defect", ["missing", "duplicate", "digest", "repository", "source"])
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
    else:
        environment["SOURCE_COMMIT"] = "d" * 40
    path.write_text(content)
    with pytest.raises(ValueError):
        delivery.publication(environment)


def test_every_cluster_or_optional_stage_runs_for_develop_only():
    pipeline = (ROOT / "ci/pipelines/dev.groovy").read_text()
    for stage, actions in (("Deploy (registry)", "env.DELIVERY_ACTION in ['deploy', 'fresh-install']"),
                           ("Build (services)", "env.DELIVERY_ACTION == 'deploy'"),
                           ("Deploy (services)", "env.DELIVERY_ACTION == 'deploy'")):
        definition = pipeline.split("stage('" + stage + "')", 1)[1].split("steps {", 1)[0]
        assert actions in definition
        assert "branch 'develop'" in definition
        assert "not { changeRequest() }" in definition
    publication = pipeline.split("stage('Publish')", 1)[1].split("steps {", 1)[0]
    assert "branch 'develop'" in publication and "not { changeRequest() }" in publication
    assert "DELIVERY_ACTION" not in publication
    assert "COORDINATE_SERVICES', defaultValue: false" in pipeline
    assert "ci-output/native-worker-save/**" in pipeline
    assert "check_native_worker_save.py" in (ROOT / "ci/build/images.sh").read_text()
    assert "choices: ['deploy', 'fresh-install']" in pipeline
    assert "publish-only" not in pipeline.split("parameters {", 1)[1].split("stages {", 1)[0]
    assert "RESET_ACTION" not in pipeline


def test_fresh_install_runs_only_its_own_script_with_the_backup_key():
    pipeline = (ROOT / "ci/pipelines/dev.groovy").read_text()
    deploy = pipeline.split("stage('Deploy (registry)')", 1)[1].split("stage('Build (services)')", 1)[0]
    fresh = deploy.split("if (env.DELIVERY_ACTION == 'fresh-install')", 1)[1].split("} else {", 1)[0]
    assert "farmer-new-dev-backup-ssh" in fresh and "ci/deploy/fresh-install-dev.sh" in fresh
    assert "deploy-dev.sh" not in fresh
    assert "ci/deploy/fresh-install-dev.sh" not in deploy.split("} else {", 1)[1]


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


def test_the_pin_proposal_is_followed_only_by_chart_publication_and_cannot_fail_the_build():
    pipeline = (ROOT / "ci/pipelines/dev.groovy").read_text()
    tail = pipeline.split("stage('Propose chart pin update')", 1)[1].split("    post {", 1)[0]
    stage = tail.split("stage('Publish chart')", 1)[0]
    assert tail.count("stage(") == 1                                # only the chart publication follows it
    definition = stage.split("steps {", 1)[0]
    assert "branch 'develop'" in definition and "not { changeRequest() }" in definition
    assert "env.DELIVERY_ACTION == 'deploy'" in definition         # not after a fresh install
    assert "agent { label 'vpn-agent2' }" in definition
    assert "catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE')" in stage
    assert "PIN_PR_CRED_ID = 'oan-ci-app'" in pipeline
    assert "credentialsId: \"${PIN_PR_CRED_ID}\"" in stage
    assert "ci/deploy/propose_pin_pr.py" in stage
    assert "VALIDATION_IMAGE" in stage


def test_a_failed_deploy_never_reaches_the_pin_proposal():
    # Declarative pipelines skip later stages once the build has failed; the registry deploy has no catchError.
    pipeline = (ROOT / "ci/pipelines/dev.groovy").read_text()
    deploy = pipeline.split("stage('Deploy (registry)')", 1)[1].split("stage('Build (services)')", 1)[0]
    assert "catchError" not in deploy
