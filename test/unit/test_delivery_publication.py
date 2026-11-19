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
TAG = "0.0.0-develop.42"
names = module("image_names", "ci/deploy/image_names.py")
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
    path.write_text("".join(f"{component}\t{ECR}/{names.repository(component)}:{TAG}\tsha256:{'c' * 64}\n"
                            for component in COMPONENTS), encoding="utf-8")
    return {"ECR_REGISTRY": ECR, "IMAGE_TAG": TAG, "SOURCE_COMMIT": COMMIT,
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


@pytest.mark.parametrize("defect", ["missing", "duplicate", "digest", "repository", "legacy", "tag", "source"])
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
        content = content.replace("/eoan/farmer-registry/", "/eoan/another/")
    elif defect == "legacy":                                       # pushed under the names before eoan
        content = content.replace(names.repository("celery"), "openg2p/farmer-registry/celery")
    elif defect == "tag":                                          # the commit12 tag of the names before eoan
        content = content.replace(TAG, COMMIT[:12])
        environment["IMAGE_TAG"] = COMMIT[:12]
    else:
        # The tag is the build number now, so the commit is checked for its form: a full SHA.
        environment["SOURCE_COMMIT"] = COMMIT[:12]
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
    assert "parameters {" not in pipeline and "params." not in pipeline
    assert "(env.COORDINATE_SERVICES ?: 'true') != 'false'" in pipeline
    assert "ci-output/native-worker-save/**" in pipeline
    assert "check_native_worker_save.py" in (ROOT / "ci/build/images.sh").read_text()
    operator = (ROOT / "ci/pipelines/operator.groovy").read_text()
    assert "'fresh-install'" in operator and "submitter: 'admin'" in operator
    assert "publish-only" not in operator
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


def test_the_chart_the_build_packaged_is_the_one_it_deploys_and_publishes():
    pipeline = (ROOT / "ci/pipelines/dev.groovy").read_text()
    packaged = pipeline.split("stage('Package chart')", 1)[1].split("stage('Deploy (package)')", 1)[0]
    assert "ci/deploy/package_chart.py package" in packaged and "stash name: 'built-chart'" in packaged
    assert "catchError" not in packaged                            # no chart, no deploy
    deploy = pipeline.split("stage('Deploy (registry)')", 1)[1].split("stage('Build (services)')", 1)[0]
    assert "unstash 'built-chart'" in deploy and deploy.count('export BUILT_CHART_DIR="$PWD/built-chart"') == 2
    publish = pipeline.split("stage('Publish chart')", 1)[1].split("    post {", 1)[0]
    assert "unstash 'built-chart'" in publish and "ci/deploy/package_chart.py publish" in publish
    assert "Propose chart pin update" not in pipeline


def test_the_built_chart_is_refused_outside_dev():
    for name in ("deploy-rc.sh", "fresh-install-dev.sh"):
        shell = (ROOT / "ci/deploy" / name).read_text()
        assert 'test "${DELIVERY_ENVIRONMENT:-dev}" = dev' in shell and "OAN_BUILT_CHART_PIN" in shell


def test_a_failed_deploy_never_reaches_chart_publication():
    # Declarative pipelines skip later stages once the build has failed; the registry deploy has no catchError.
    pipeline = (ROOT / "ci/pipelines/dev.groovy").read_text()
    deploy = pipeline.split("stage('Deploy (registry)')", 1)[1].split("stage('Build (services)')", 1)[0]
    assert "catchError" not in deploy


def test_the_chart_version_is_the_image_tag_of_init_yaml():
    import sys
    sys.path.insert(0, str(ROOT / "ci/deploy"))
    package = module("package_chart", "ci/deploy/package_chart.py")
    version = names.chart_version()
    assert package.chart_version({"IMAGE_TAG": version + "-develop.57"}) == version + "-develop.57"
    for tag in ("0.0.0-develop.57" if version != "0.0.0" else "9.9.9-develop.57", "abcdef012345", version + "-develop"):
        with pytest.raises(ValueError):
            package.chart_version({"IMAGE_TAG": tag})
