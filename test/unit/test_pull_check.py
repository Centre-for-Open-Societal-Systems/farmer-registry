"""ci/deploy/pull_check.py against a stand-in kubectl: which images are checked, how a pod's status is read, cleanup."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pull_check", ROOT / "ci/deploy/pull_check.py")
pull_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pull_check)

HOST = "123456789012.dkr.ecr.ap-south-1.amazonaws.com"
A = "sha256:" + "a" * 64
B = "sha256:" + "b" * 64
VALUES = f"""registry:
  staffApi:
    image:
      repository: {HOST}/eoan/farmer-registry/staff-api-1.2.2-rc.625
      tag: "1.0.0-develop.57@{A}"
  celery:
    image:
      repository: "{HOST}/eoan/farmer-registry/celery-1.2.2-rc.625"
      tag: 1.0.0-develop.57@{B}
  celeryBeat:
    image:
      repository: {HOST}/eoan/farmer-registry/celery-1.2.2-rc.625
      tag: 1.0.0-develop.57@{B}
dashboardApi:
  image:
    repository: {HOST}/eoan/farmer-registry/dashboard-api
    tag: 1.0.0-develop.12
"""


def waiting(reason):
    return {"containerStatuses": [{"state": {"waiting": {"reason": reason}}}]}


def test_only_digest_pinned_images_are_checked_once_each():
    assert pull_check.pinned_images(VALUES) == [
        f"{HOST}/eoan/farmer-registry/staff-api-1.2.2-rc.625@{A}", f"{HOST}/eoan/farmer-registry/celery-1.2.2-rc.625@{B}"]


def test_images_are_read_from_the_chart_archive(tmp_path):
    archive = tmp_path / "chart.tgz"
    data = VALUES.encode()
    with tarfile.open(archive, "w:gz") as bundle:
        info = tarfile.TarInfo("openg2p-farmer-registry/values.yaml")
        info.size = len(data)
        bundle.addfile(info, io.BytesIO(data))
        nested = tarfile.TarInfo("openg2p-farmer-registry/charts/registry/values.yaml")
        nested.size = 0
        bundle.addfile(nested, io.BytesIO(b""))
    assert len(pull_check.chart_images(archive)) == 2


def test_pod_status_is_read_as_pulled_failed_or_undecided():
    assert pull_check.pulled({"containerStatuses": [{"state": {"terminated": {"exitCode": 0}}}]}) is True
    assert pull_check.pulled({"containerStatuses": [{"state": {"running": {}}}]}) is True
    assert pull_check.pulled(waiting("CreateContainerConfigError")) is True
    assert pull_check.pulled(waiting("ErrImagePull")) is False
    assert pull_check.pulled(waiting("ImagePullBackOff")) is False
    assert pull_check.pulled(waiting("ContainerCreating")) is None
    assert pull_check.pulled({}) is None


def test_the_pod_is_locked_down_and_pulls_from_the_registry():
    spec = pull_check.pod("p", "farmer", "x@" + A, "r")["spec"]
    container = spec["containers"][0]
    assert container["imagePullPolicy"] == "Always" and container["command"] == ["true"]
    assert spec["securityContext"]["runAsNonRoot"] and container["securityContext"]["capabilities"] == {"drop": ["ALL"]}
    assert spec["automountServiceAccountToken"] is False and spec["restartPolicy"] == "Never"


class Cluster:
    def __init__(self, states):
        self.states, self.calls, self.created = states, [], {}

    def __call__(self, args, stdin=None):
        self.calls.append(args)
        if args[0] == "apply":
            manifest = json.loads(stdin)
            self.created[manifest["metadata"]["name"]] = manifest["spec"]["containers"][0]["image"]
            return ""
        if args[0] == "get":
            image = self.created[args[2]]
            sequence = self.states[image]
            return json.dumps({"status": sequence.pop(0) if len(sequence) > 1 else sequence[0]})
        return ""


def test_every_image_pulled_and_the_pods_are_removed():
    cluster = Cluster({"one": [waiting("ContainerCreating"), {"containerStatuses": [{"state": {"terminated": {}}}]}],
                       "two": [{"containerStatuses": [{"state": {"running": {}}}]}]})
    assert pull_check.check("farmer", ["one", "two"], timeout=60, delay=0, call=cluster, sleep=lambda _: None) == \
        {"one": True, "two": True}
    delete = cluster.calls[-1]
    assert delete[:2] == ["delete", "pod"] and delete[delete.index("-l") + 1].startswith(pull_check.LABEL + "=")


def test_a_pull_error_fails_and_the_pods_are_still_removed():
    cluster = Cluster({"one": [waiting("ImagePullBackOff")], "two": [{"containerStatuses": [{"state": {"running": {}}}]}]})
    assert pull_check.check("farmer", ["one", "two"], timeout=60, delay=0, call=cluster, sleep=lambda _: None) == \
        {"one": False, "two": True}
    assert cluster.calls[-1][0] == "delete"


def test_no_answer_in_time_is_not_a_pull():
    ticks = iter(range(0, 1000, 10))
    cluster = Cluster({"one": [waiting("ContainerCreating")]})
    assert pull_check.check("farmer", ["one"], timeout=30, delay=0, call=cluster, clock=lambda: next(ticks),
                            sleep=lambda _: None) == {"one": None}
    assert cluster.calls[-1][0] == "delete"


def test_main_fails_when_any_image_cannot_be_pulled(tmp_path, monkeypatch, capsys):
    archive = tmp_path / "chart.tgz"
    data = VALUES.encode()
    with tarfile.open(archive, "w:gz") as bundle:
        info = tarfile.TarInfo("openg2p-farmer-registry/values.yaml")
        info.size = len(data)
        bundle.addfile(info, io.BytesIO(data))
    monkeypatch.setattr(pull_check, "check", lambda namespace, images, timeout: {images[0]: True, images[1]: False})
    assert pull_check.main(["--namespace", "farmer", "--chart", str(archive)]) == 1
    out = capsys.readouterr()
    assert "PULL FAILED" in out.out and "nothing was deployed" in out.err


def test_both_deliveries_check_the_pull_before_they_deploy():
    dev = (ROOT / "ci/pipelines/dev.groovy").read_text()
    deploy = dev.split("stage('Deploy (registry)')", 1)[1].split("stage('Build (services)')", 1)[0]
    assert deploy.index("ci/deploy/pull_check.py --namespace farmer --chart") < deploy.index("bash ci/deploy/deploy-dev.sh")
    assert deploy.index("ci/deploy/pull_check.py") < deploy.index("bash ci/deploy/fresh-install-dev.sh")
    staging = (ROOT / "ci/deploy/promote-staging.sh").read_text()
    assert "DRY_RUN=1 python3 .oan-helm/scripts/ci/promote_chart.py" in staging
    assert staging.index("ci/deploy/pull_check.py") < staging.index("deliver_staging.sh openg2p-farmer-registry")
