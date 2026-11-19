"""The staff UI's registry-platform commit must be the one OpenG2P built openg2p/openg2p-registry-staff-ui:<rpVersion> from.

<rpVersion> is the ARG BASE_IMAGE_VERSION default of the platform Dockerfiles and <rpCommit> the one of
docker/staff-ui/Dockerfile (ci/deploy/image_names.py platform, platform-commit).

The staff UI image is rebuilt from rpCommit, so a platform bump that leaves rpCommit
behind would build an older UI under the new platform version. The commit is the org.opencontainers.image.revision
label of the published image, read anonymously from the Docker Hub registry API (manifest and config only, no layers).

    python3 ci/build/check_rp_commit.py <rpVersion> <rpCommit>

Standard library only. Exit codes: 0 match, 1 mismatch or the label cannot be read.
"""
import json
import sys
import urllib.parse
import urllib.request

REPOSITORY = "openg2p/openg2p-registry-staff-ui"
REGISTRY = "https://registry-1.docker.io/v2/"
AUTH = "https://auth.docker.io/token"
LABEL = "org.opencontainers.image.revision"
MANIFESTS = ", ".join((
    "application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json"))


def fetch(url, token, accept=None):
    headers = {"Authorization": "Bearer " + token}
    if accept:
        headers["Accept"] = accept
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def anonymous_token(repository):
    query = urllib.parse.urlencode({"service": "registry.docker.io", "scope": "repository:%s:pull" % repository})
    with urllib.request.urlopen(AUTH + "?" + query, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))["token"]


def revision(version, get=fetch, token=None):
    """The revision label of the linux/amd64 image of REPOSITORY:version."""
    token = token or anonymous_token(REPOSITORY)
    base = REGISTRY + REPOSITORY
    manifest = get("%s/manifests/%s" % (base, version), token, MANIFESTS)
    if "manifests" in manifest:
        chosen = [m for m in manifest["manifests"]
                  if (m.get("platform") or {}).get("os") == "linux" and (m.get("platform") or {}).get("architecture") == "amd64"]
        if not chosen:
            raise ValueError("%s:%s has no linux/amd64 image" % (REPOSITORY, version))
        manifest = get("%s/manifests/%s" % (base, chosen[0]["digest"]), token, MANIFESTS)
    config = get("%s/blobs/%s" % (base, manifest["config"]["digest"]), token)
    return ((config.get("config") or {}).get("Labels") or {}).get(LABEL)


def main(argv, get=fetch, token=None):
    if len(argv) != 3:
        print("usage: check_rp_commit.py <rpVersion> <rpCommit>", file=sys.stderr)
        return 1
    version, commit = argv[1], argv[2]
    try:
        found = revision(version, get, token)
    except (OSError, ValueError, KeyError) as error:
        print("FAIL: could not read %s of %s:%s: %s" % (LABEL, REPOSITORY, version, error), file=sys.stderr)
        return 1
    if found != commit:
        print("FAIL: docker/staff-ui/Dockerfile BASE_IMAGE_VERSION is %s, but %s:%s was built from %s. "
              "Set both with scripts/bump-rp-version.sh." % (commit, REPOSITORY, version, found or "<no revision label>"),
              file=sys.stderr)
        return 1
    print("rpCommit matches %s:%s" % (REPOSITORY, version))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
