"""After a successful deploy: package helm/openg2p-farmer-registry with this build's images and publish it.

Run by the stage "Publish chart" of every develop build. The chart version comes from git (OpenG2P's policy, in
scripts/ci/derive-version.sh of oan-helm), so the chart and images of a commit always belong together and nothing is
committed back. The image tags and digests are written into the packaged copy only.

oan-helm's publisher (scripts/ci/publish_chart.py) adds the archive to repository/develop/ and its workflow updates the
index, CHANGELOG.md and the per-chart rollback history from the annotations set here.

Needs GH_TOKEN with push access to oan-helm, IMAGE_TAG, SOURCE_COMMIT, ECR_REGISTRY, ECR_REPOSITORY, BRANCH_NAME and
COMMIT_SUBJECT. DRY_RUN=1 packages the chart and publishes nothing. Standard library only: it runs on the Jenkins agent.

Exit codes: 0 published (or already published by an earlier run of this commit), 1 failure, 3 no credential.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import release_images  # noqa: E402

CHART = "openg2p-farmer-registry"
OAN_HELM = "https://github.com/Centre-for-Open-Societal-Systems/oan-helm.git"
ALREADY_PUBLISHED = 4


def annotate(text, notes):
    """The Chart.yaml text with `notes` added under annotations:, values quoted."""
    lines = text.split("\n")
    at = lines.index("annotations:") + 1
    lines[at:at] = ["  %s: %s" % (key, json.dumps(value)) for key, value in sorted(notes.items())]
    return "\n".join(lines)


def run(command, cwd=None, env=None):
    return subprocess.run(command, cwd=str(cwd or ROOT), env=env, check=True, stdout=subprocess.PIPE,
                          universal_newlines=True).stdout


def fetch_publisher(work):
    """scripts/ci of oan-helm main, without its repository/ archives."""
    target = work / "oan-helm"
    run(["git", "clone", "--quiet", "--depth", "1", "--filter=blob:none", "--sparse", OAN_HELM, str(target)])
    run(["git", "sparse-checkout", "set", "scripts/ci"], cwd=target)
    return target / "scripts/ci"


def derive_version(scripts, branch):
    if run(["git", "rev-parse", "--is-shallow-repository"]).strip() != "false":
        raise ValueError("a shallow clone cannot give the commit count the version needs")
    out = run(["bash", str(scripts / "derive-version.sh")], env=dict(os.environ, REF_NAME=branch, REF_TYPE="branch"))
    return re.search(r"(?m)^version=(\S+)$", out).group(1)


def package(env, version, work):
    source = ROOT / "helm" / CHART
    chart = work / "chart" / CHART
    shutil.copytree(str(source), str(chart))
    digests = release_images.read_digests((ROOT / release_images.DIGESTS).read_text(encoding="utf-8"),
                                          env["ECR_REGISTRY"], env["ECR_REPOSITORY"], env["IMAGE_TAG"])
    values = chart / "values.yaml"
    values.write_text(release_images.rewrite_values(
        values.read_text(encoding="utf-8"), release_images.wanted(env["IMAGE_TAG"], digests),
        release_images.expected_repositories(env["ECR_REGISTRY"], env["ECR_REPOSITORY"])), encoding="utf-8")
    metadata = chart / "Chart.yaml"
    metadata.write_text(annotate(metadata.read_text(encoding="utf-8"), {
        "oan.org/source-repository": "Centre-for-Open-Societal-Systems/farmer-registry",
        "oan.org/source-commit": env["SOURCE_COMMIT"],
        "oan.org/source-subject": env.get("COMMIT_SUBJECT", "")[:200],
        "oan.org/release-name": "farmer-registry",
        "oan.org/release-namespace": "farmer",
        "oan.org/values-overlay": "environments/dev/values/farmer.yaml",
    }), encoding="utf-8")
    run(["helm", "repo", "add", "--force-update", "openg2p", "https://openg2p.github.io/openg2p-helm"])
    run(["helm", "dependency", "build", str(chart)])
    run(["helm", "package", str(chart), "--version", version, "--destination", str(work / "dist")])
    return work / "dist" / ("%s-%s.tgz" % (CHART, version))


def main(env=None):
    env = dict(os.environ if env is None else env)
    dry = env.get("DRY_RUN") == "1"
    if not dry and not env.get("GH_TOKEN"):
        print("FAIL: no GitHub credential: the chart was not published.")
        return 3
    work = Path(tempfile.mkdtemp(prefix="farmer-chart-"))
    try:
        scripts = fetch_publisher(work)
        version = derive_version(scripts, env["BRANCH_NAME"])
        archive = package(env, version, work)
        result = subprocess.run([sys.executable, str(scripts / "publish_chart.py"), str(archive)], env=env)
        if result.returncode == ALREADY_PUBLISHED:
            print("%s %s was published by an earlier run of this commit." % (CHART, version))
            return 0
        return result.returncode
    except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print("FAIL: %s: %s" % (error.__class__.__name__, error))
        return 1
    finally:
        shutil.rmtree(str(work), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
