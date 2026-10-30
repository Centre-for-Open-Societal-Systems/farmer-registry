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


@pytest.mark.parametrize("environment", [{}, {"DELIVERY_ACTION": ""}, {"DELIVERY_ACTION": "publish-only"}])
def test_first_build_or_explicit_publication_never_selects_deployment(environment):
    assert delivery.action(environment) == "publish-only"


@pytest.mark.parametrize("selected", ["deploy", "fresh-install"])
def test_cluster_actions_are_explicit_choices(selected):
    assert delivery.action({"DELIVERY_ACTION": selected}) == selected


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
            "DELIVERY_ACTION": "publish-only"}, path


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


def test_every_cluster_or_optional_stage_requires_explicit_deploy():
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
    # Publication is only skipped for the connector-only actions, never selected by deploy actions.
    assert publication.count("DELIVERY_ACTION") == 1
    assert "!(env.DELIVERY_ACTION in ['connector-plan', 'connector-upgrade'])" in publication
    assert "COORDINATE_SERVICES', defaultValue: false" in pipeline
    assert "ci-output/native-worker-save/**" in pipeline
    assert "check_native_worker_save.py" in (ROOT / "ci/build/images.sh").read_text()
    assert "choices: ['publish-only', 'deploy', 'fresh-install', 'connector-plan', 'connector-upgrade']" in pipeline
    assert "RESET_ACTION" not in pipeline


def test_connector_actions_build_nothing_and_run_only_the_connector_script():
    pipeline = (ROOT / "ci/pipelines/dev.groovy").read_text()
    build = pipeline.split("stage('Build')", 1)[1].split("steps {", 1)[0]
    assert "!(env.DELIVERY_ACTION in ['connector-plan', 'connector-upgrade'])" in build
    stage = pipeline.split("stage('Upgrade connector (dev)')", 1)[1].split("post {", 1)[0]
    head = stage.split("steps {", 1)[0]
    assert "env.DELIVERY_ACTION in ['connector-plan', 'connector-upgrade']" in head
    assert "branch 'develop'" in head and "not { changeRequest() }" in head
    plan, upgrade = stage.split("} else {", 1)
    assert "PLAN_ONLY=1 bash ci/connector/upgrade-farmer-connector.sh" in plan
    assert "farmer-new-dev-backup-ssh" not in plan
    assert "farmer-new-dev-backup-ssh" in upgrade and "PLAN_ONLY" not in upgrade
    assert delivery.action({"DELIVERY_ACTION": "connector-plan"}) == "connector-plan"
    assert delivery.action({"DELIVERY_ACTION": "connector-upgrade"}) == "connector-upgrade"
    for bad in ("connector", "connector-rollback"):
        with pytest.raises(ValueError):
            delivery.action({"DELIVERY_ACTION": bad})


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
