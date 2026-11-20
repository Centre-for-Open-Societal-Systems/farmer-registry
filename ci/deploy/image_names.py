"""The ECR names of the Farmer Registry images (oan-helm docs/release/naming-standard.md, section 6).

    eoan/farmer-registry/<image>[-<rpVersion>]:<version>-<branch>.<build>

    eoan/farmer-registry/staff-api-1.2.2-rc.625:1.0.0-develop.57     an OpenG2P platform role
    eoan/farmer-registry/registry-connector-api:1.0.0-develop.57     any other image

<version> is in init.yaml at the root of this repository. <rpVersion>, the OpenG2P registry platform the images are
built on, is where OpenG2P keeps it: the `ARG BASE_IMAGE_VERSION=<rpVersion>` default of every docker/<role>/Dockerfile
built FROM a platform image, all the same (test/unit/test_base_image_pin_lockstep.py; scripts/bump-rp-version.sh
changes them together). The staff UI Dockerfile's default is the registry-platform commit of that version's staff UI.
Only the six images built on the platform carry -<rpVersion> in their repository name, so a platform bump starts new
repositories for them. <build> is the Jenkins build number. The pipeline, the chart packaging and the deployment
guards all take the names from here.

Releases deployed before these names still run images of openg2p/farmer-registry/<image>:<commit12>; a guard that
reads an installed release accepts those too (legacy_repository).

    image_names.py tag <branch> <build>     the image tag of a build
    image_names.py repository <image>       the ECR repository of an image, without the registry host
    image_names.py legacy <image>           its repository before eoan (the settings template of a new repository)
    image_names.py platform                 rpVersion, from the platform Dockerfiles
    image_names.py platform-commit          the staff UI Dockerfile's registry-platform commit

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
FIELDS = ("version",)
VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
RP_VERSION = re.compile(VERSION.pattern + r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")
COMMIT = re.compile(r"[0-9a-f]{40}")
DOCKER = ROOT / "docker"
# The Dockerfiles built FROM openg2p/openg2p-registry-<role>:${BASE_IMAGE_VERSION}; the staff UI is rebuilt from source.
PLATFORM_DOCKERFILES = ("staff-api", "partner-api", "celery", "db-seed", "sanity-tests")
DEFAULT = re.compile(r"(?m)^ARG BASE_IMAGE_VERSION=(\S+)\s*$")
LINE = re.compile(r"""^(?P<key>[A-Za-z][A-Za-z0-9_]*)\s*:\s*(?P<value>"[^"]*"|'[^']*'|[^#\s]+)\s*(?:#.*)?$""")
TAG = re.compile(r"\d+\.\d+\.\d+-[a-z0-9]+(?:-[a-z0-9]+)*\.[1-9]\d*")
IMAGE = re.compile(r"\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com/(?P<repository>[^:@\s]+)"
                   r":(?P<tag>[A-Za-z0-9_.-]+)@sha256:[0-9a-f]{64}")


def read_init(path=None):
    """init.yaml as {field: value}: flat `key: value` lines and comments, version and nothing else."""
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
    if not VERSION.fullmatch(fields.get("version", "")):
        raise ValueError("%s: version is missing or not N.N.N" % path.name)
    return fields


def dockerfile_default(role, docker=None):
    """The ARG BASE_IMAGE_VERSION default of docker/<role>/Dockerfile."""
    path = Path(docker or DOCKER) / role / "Dockerfile"
    found = DEFAULT.findall(path.read_text(encoding="utf-8"))
    if len(found) != 1:
        raise ValueError("%s must declare ARG BASE_IMAGE_VERSION=<value> once" % path.relative_to(path.parents[2]))
    return found[0]


def platform_version(docker=None):
    """rpVersion: the one default every platform Dockerfile declares."""
    pins = {role: dockerfile_default(role, docker) for role in PLATFORM_DOCKERFILES}
    values = set(pins.values())
    if len(values) != 1:
        raise ValueError("the platform Dockerfiles differ: %s; change them together with scripts/bump-rp-version.sh"
                         % ", ".join("%s=%s" % item for item in sorted(pins.items())))
    version = values.pop()
    if not RP_VERSION.fullmatch(version):
        raise ValueError("BASE_IMAGE_VERSION %r is not a SemVer version" % version)
    return version


def platform_commit(docker=None):
    """The registry-platform commit the staff UI is rebuilt from: its Dockerfile's default."""
    commit = dockerfile_default("staff-ui", docker)
    if not COMMIT.fullmatch(commit):
        raise ValueError("docker/staff-ui/Dockerfile BASE_IMAGE_VERSION %r is not a commit" % commit)
    return commit


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
    elif sys.argv[1:] == ["platform"]:
        print(platform_version())
    elif sys.argv[1:] == ["platform-commit"]:
        print(platform_commit())
    else:
        raise ValueError("usage: image_names.py tag <branch> <build> | repository <image> | legacy <image>"
                         " | platform | platform-commit")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit("FAIL: %s" % error)
