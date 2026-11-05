"""Package helm/openg2p-farmer-registry with this build's images, and publish that same archive after the deploy.

Two stages of every develop build run this script:

    package_chart.py package   before the deploy: writes built-chart/<chart>-<version>.tgz and built-chart/pin.json
    package_chart.py publish   after a successful deploy: adds that archive to repository/develop/ of oan-helm

The deploy installs built-chart/ (BUILT_CHART_DIR in deploy-rc.sh), so New Dev runs exactly the archive that is published.

The chart version comes from git (OpenG2P's policy, in scripts/ci/derive-version.sh of oan-helm), so the chart and images
of a commit always belong together and nothing is committed back. The image tags and digests are written into the
packaged copy only. oan-helm's publisher (scripts/ci/publish_chart.py) adds the archive and its workflow updates the
index, CHANGELOG.md and the per-chart rollback history from the annotations set here.

package needs IMAGE_TAG, SOURCE_COMMIT, ECR_REGISTRY, ECR_REPOSITORY, BRANCH_NAME and COMMIT_SUBJECT. publish needs
GH_TOKEN with push access to oan-helm; DRY_RUN=1 publishes nothing. Standard library only: it runs on the Jenkins agent.

Exit codes: 0 done (or already published by an earlier run of this commit), 1 failure, 3 no credential.
"""
import hashlib
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
OUTPUT = ROOT / "built-chart"


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
    run(["helm", "package", str(chart), "--version", version, "--destination", str(OUTPUT)])
    return OUTPUT / ("%s-%s.tgz" % (CHART, version))


def pin(archive, version):
    """The pin of this archive, in the shape of ci/deploy/oan-chart.json: what ci/deploy/oan_chart.py verifies."""
    metadata = (ROOT / "helm" / CHART / "Chart.yaml").read_text(encoding="utf-8")
    return {
        "name": CHART,
        "version": version,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "platformVersion": re.search(r"(?m)^appVersion: (\S+)$", metadata).group(1),
        "environment": "dev",
        "namespace": "farmer",
        "release": "farmer-registry",
    }


def package_build(env, work):
    shutil.rmtree(str(OUTPUT), ignore_errors=True)
    OUTPUT.mkdir()
    version = derive_version(fetch_publisher(work), env["BRANCH_NAME"])
    archive = package(env, version, work)
    (OUTPUT / "pin.json").write_text(json.dumps(pin(archive, version), indent=2) + "\n", encoding="utf-8")
    print("packaged %s" % archive.name)
    return 0


def publish_build(env, work):
    if env.get("DRY_RUN") != "1" and not env.get("GH_TOKEN"):
        print("FAIL: no GitHub credential: the chart was not published.")
        return 3
    archives = sorted(OUTPUT.glob("*.tgz"))
    if len(archives) != 1:
        raise ValueError("expected the one archive of this build in %s" % OUTPUT)
    scripts = fetch_publisher(work)
    result = subprocess.run([sys.executable, str(scripts / "publish_chart.py"), str(archives[0])], env=env)
    if result.returncode == ALREADY_PUBLISHED:
        print("%s was published by an earlier run of this commit." % archives[0].name)
        return 0
    return result.returncode


def main(argv=None, env=None):
    argv = sys.argv[1:] if argv is None else argv
    env = dict(os.environ if env is None else env)
    actions = {"package": package_build, "publish": publish_build}
    if len(argv) != 1 or argv[0] not in actions:
        print("usage: package_chart.py package|publish")
        return 1
    work = Path(tempfile.mkdtemp(prefix="farmer-chart-"))
    try:
        return actions[argv[0]](env, work)
    except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print("FAIL: %s: %s" % (error.__class__.__name__, error))
        return 1
    finally:
        shutil.rmtree(str(work), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
