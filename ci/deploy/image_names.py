"""The ECR names of the Farmer Registry images: eoan/farmer-registry/<image>-<RP version>:<version>-<branch>.<build>.

    eoan/farmer-registry/staff-ui-1.2.2-rc.625:0.0.0-develop.300

The RP version is appVersion of helm/openg2p-farmer-registry/Chart.yaml (the OpenG2P registry platform the images are
built on) and <version> is that chart's version, so both move with Chart.yaml and nothing else holds them. <build> is the
Jenkins build number. The pipeline, the chart packaging and the deployment guards all take the names from here.

Releases deployed before these names still run images of openg2p/farmer-registry/<image>:<commit12>; a guard that
reads an installed release accepts those too (legacy_repository).

    image_names.py tag <branch> <build>     the image tag of a build
    image_names.py repository <image>       the ECR repository of an image, without the registry host

Standard library only: it runs on the Jenkins agent's stock Python.
"""
import re
import sys
from pathlib import Path

CHART = Path(__file__).resolve().parents[2] / "helm/openg2p-farmer-registry/Chart.yaml"
PATH = "eoan/farmer-registry"
LEGACY_PATH = "openg2p/farmer-registry"
TAG = re.compile(r"\d+\.\d+\.\d+-[a-z0-9]+(?:-[a-z0-9]+)*\.[1-9]\d*")
IMAGE = re.compile(r"\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com/(?P<repository>[^:@\s]+)"
                   r":(?P<tag>[A-Za-z0-9_.-]+)@sha256:[0-9a-f]{64}")


def _chart_field(name):
    match = re.search(r"""(?m)^%s:\s*["']?([^"'\s]+)""" % name, CHART.read_text(encoding="utf-8"))
    if not match:
        raise ValueError("%s has no %s" % (CHART.name, name))
    return match.group(1)


def platform_version():
    return _chart_field("appVersion")


def chart_version():
    return _chart_field("version")


def repository(image):
    return "%s/%s-%s" % (PATH, image, platform_version())


def legacy_repository(image):
    return "%s/%s" % (LEGACY_PATH, image)


def is_repository(value, image):
    """True for a repository of `image` under any platform version, or its name before eoan: what a release may run."""
    return (value == legacy_repository(image)
            or re.fullmatch(r"%s/%s-\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?" % (re.escape(PATH), re.escape(image)), value) is not None)


def is_pinned_image(image, component, commit=None):
    """True for an ap-south-1 ECR image of `component` pinned by tag and digest.

    Under the eoan names the tag is image_names.py's; under the names before eoan it is the commit12 tag (of `commit`,
    when given).
    """
    match = IMAGE.fullmatch(image or "")
    if not match or not is_repository(match.group("repository"), component):
        return False
    if match.group("repository") == legacy_repository(component):
        return re.fullmatch(re.escape(commit[:12]) if commit else r"[0-9a-f]{12}", match.group("tag")) is not None
    return is_tag(match.group("tag"))


def tag(branch, build):
    slug = re.sub(r"[^a-z0-9]+", "-", branch.lower()).strip("-")
    if not slug or not re.fullmatch(r"[1-9]\d*", str(build)):
        raise ValueError("an image tag needs a branch and a build number")
    return "%s-%s.%s" % (chart_version(), slug, build)


def is_tag(value):
    return TAG.fullmatch(value) is not None


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "tag":
        print(tag(sys.argv[2], sys.argv[3]))
    elif len(sys.argv) == 3 and sys.argv[1] == "repository":
        print(repository(sys.argv[2]))
    else:
        raise ValueError("usage: image_names.py tag <branch> <build> | repository <image>")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit("FAIL: %s" % error)
