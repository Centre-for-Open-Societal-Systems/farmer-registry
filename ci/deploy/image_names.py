"""The ECR names of the Farmer Registry images (oan-helm docs/release/naming-standard.md, section 6).

    eoan/farmer-registry/<image>[-<rpVersion>]:<version>-<branch>.<build>

    eoan/farmer-registry/staff-api-1.2.2-rc.625:1.0.0-develop.57     an OpenG2P platform role
    eoan/farmer-registry/registry-connector-api:1.0.0-develop.57     any other image

version, rpVersion and rpCommit are in init.yaml at the root of this repository, the only place they are written by
hand (scripts/bump-rp-version.sh changes rpVersion). Only the six images built on the OpenG2P registry platform carry
-<rpVersion> in their repository name, so a platform bump starts new repositories for them. <build> is the Jenkins
build number. The pipeline, the chart packaging and the deployment guards all take the names from here.

Releases deployed before these names still run images of openg2p/farmer-registry/<image>:<commit12>; a guard that
reads an installed release accepts those too (legacy_repository).

    image_names.py tag <branch> <build>     the image tag of a build
    image_names.py repository <image>       the ECR repository of an image, without the registry host
    image_names.py legacy <image>           its repository before eoan (the settings template of a new repository)
    image_names.py field <name>             version, rpVersion or rpCommit from init.yaml

Standard library only: it runs on the Jenkins agent's stock Python.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INIT = ROOT / "init.yaml"
PATH = "eoan/farmer-registry"
LEGACY_PATH = "openg2p/farmer-registry"
# The OpenG2P registry platform roles: their images are built FROM openg2p/openg2p-registry-<role>:<rpVersion>.
PLATFORM_IMAGES = ("staff-ui", "staff-api", "partner-api", "celery", "db-seed", "sanity-tests")
# The connector API image (docker/registry-connector) is published as registry-connector-api, beside
# registry-connector-ui, as OpenG2P names the connector's images; before eoan it was openg2p/farmer-registry/registry-connector.
RENAMED = {"registry-connector": "registry-connector-api"}
FIELDS = ("version", "rpVersion", "rpCommit")
VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
RP_VERSION = re.compile(VERSION.pattern + r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")
COMMIT = re.compile(r"[0-9a-f]{40}")
LINE = re.compile(r"""^(?P<key>[A-Za-z][A-Za-z0-9_]*)\s*:\s*(?P<value>"[^"]*"|'[^']*'|[^#\s]+)\s*(?:#.*)?$""")
TAG = re.compile(r"\d+\.\d+\.\d+-[a-z0-9]+(?:-[a-z0-9]+)*\.[1-9]\d*")
IMAGE = re.compile(r"\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com/(?P<repository>[^:@\s]+)"
                   r":(?P<tag>[A-Za-z0-9_.-]+)@sha256:[0-9a-f]{64}")


def read_init(path=None):
    """init.yaml as {field: value}: flat `key: value` lines and comments, the three fields, nothing else."""
    path = Path(path or INIT)
    fields = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        found = LINE.match(line)
        if not found:
            raise ValueError("%s line %d is not `key: value`" % (path.name, number))
        key = found.group("key")
        if key not in FIELDS or key in fields:
            raise ValueError("%s: %s is unknown or set twice" % (path.name, key))
        fields[key] = found.group("value").strip("\"'")
    for key, pattern in (("version", VERSION), ("rpVersion", RP_VERSION), ("rpCommit", COMMIT)):
        if not pattern.fullmatch(fields.get(key, "")):
            raise ValueError("%s: %s is missing or malformed" % (path.name, key))
    return fields


def platform_version():
    return read_init()["rpVersion"]


def chart_version():
    """The release this repository works towards; builds add -<branch>.<build>."""
    return read_init()["version"]


def repository(image):
    if image in PLATFORM_IMAGES:
        return "%s/%s-%s" % (PATH, image, platform_version())
    return "%s/%s" % (PATH, RENAMED.get(image, image))


def legacy_repository(image):
    return "%s/%s" % (LEGACY_PATH, image)


def is_repository(value, image):
    """True for a repository of `image` (under any platform version for a platform role) or its name before eoan."""
    if value == legacy_repository(image):
        return True
    if image in PLATFORM_IMAGES:
        pattern = r"%s/%s-%s" % (re.escape(PATH), re.escape(image), RP_VERSION.pattern)
    else:
        pattern = r"%s/%s" % (re.escape(PATH), re.escape(RENAMED.get(image, image)))
    return re.fullmatch(pattern, value) is not None


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
    """<version>-<branch>.<build>, as oan-helm's scripts/ci/oan_version.py gives the chart of the same build."""
    slug = re.sub(r"[^a-z0-9]+", "-", branch.lower()).strip("-")
    if slug.isdigit():
        slug = "b" + slug
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
    elif len(sys.argv) == 3 and sys.argv[1] == "legacy":
        print(legacy_repository(sys.argv[2]))
    elif len(sys.argv) == 3 and sys.argv[1] == "field" and sys.argv[2] in FIELDS:
        print(read_init()[sys.argv[2]])
    else:
        raise ValueError("usage: image_names.py tag <branch> <build> | repository <image> | legacy <image> | field <name>")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit("FAIL: %s" % error)
