"""Move the pinned oan-helm Farmer chart (ci/deploy/oan-chart.json, the dev pin) to a new oan-helm commit.

It reads only from the immutable oan-helm commit you name, computes the SHA-256 of the chart archive, cross-checks
it against repository/SHA256SUMS at that commit, reads the chart and platform versions from the archive, and rewrites
the pin. It never touches a cluster. The pin changes in a reviewed pull request, never inside a deploy.

    python3 ci/deploy/bump_pin.py <40-hex oan-helm commit>             # show the new pin, change nothing
    python3 ci/deploy/bump_pin.py <commit> --write                     # update oan-chart.json
    python3 ci/deploy/bump_pin.py <commit> --version 1.0.0-dev.21      # default: releases/current.yaml
    python3 ci/deploy/bump_pin.py --latest [--write]                   # use the head of oan-helm main

--latest looks at the head of oan-helm `main`. A proposal is made only when the newest released Farmer chart has a
higher version than the pin; a different archive for the same version is an error (published archives are immutable)
and an older chart is never proposed (no downgrade). The dev release takes its values from the live release, so no
values file is pinned for dev (ci/deploy/oan-chart-staging.json is a separate pin and is never touched here).
A develop build deploys the chart it packaged itself, so this pin only serves a deploy run by hand. A platform version
change needs the images and ci/deploy/oan_compat.py to move with it (see NOTE below).

A new platform version is NOT propagated automatically: the Dockerfiles (ARG BASE_IMAGE_VERSION), the chart
dependency in helm/openg2p-farmer-registry, REVIEWED_PLATFORMS in ci/deploy/oan_compat.py, ci/environments.py,
ci/validation/native-release-contract.json and helm/environments/*/delivery.yaml all name it. Run
scripts/bump-rp-version.sh and update the others by hand.

Standard library only; runs on the deploy node's stock Python (3.7 or later).
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import urllib.request

PROFILE = Path(__file__).with_name("oan-chart.json")
ROOT = Path(__file__).resolve().parents[2]
GIT = "https://github.com/Centre-for-Open-Societal-Systems/oan-helm.git"
RAW = "https://raw.githubusercontent.com/Centre-for-Open-Societal-Systems/oan-helm/"
CHART = "openg2p-farmer-registry"
LIMIT = 32 * 1024 * 1024


def get(uri):
    with urllib.request.urlopen(uri, timeout=30) as response:
        data = response.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("download exceeds the size limit: " + uri)
    return data


def chart_appversion(archive_bytes, name):
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        member = archive.getmember(name + "/Chart.yaml")
        if not member.isfile() or member.size > 1024 * 1024:
            raise ValueError("unexpected Chart.yaml in the archive")
        text = archive.extractfile(member).read().decode("utf-8")
    found = re.search(r"(?m)^appVersion:\s*['\"]?([^'\"\s]+)", text)
    version = re.search(r"(?m)^version:\s*['\"]?([^'\"\s]+)", text)
    if not found or not version:
        raise ValueError("Chart.yaml has no appVersion/version")
    return version.group(1), found.group(1)


def archive_url(pin):
    """Where the deploy downloads the archive from (the same rule as `oan_chart.py url`)."""
    return pin["repository"] + pin["name"] + "-" + pin["version"] + ".tgz"


def new_pin(commit, version=None, fetch=get):
    """Return the updated pin (dict) for the oan-helm commit; `fetch` is injectable for tests."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("give the full 40-character oan-helm commit that contains the release")
    base = RAW + commit + "/"
    if version is None:
        current = fetch(base + "releases/current.yaml").decode("utf-8")
        found = re.search(r"(?m)^\s*" + re.escape(CHART) + r":\s*(\S+)\s*$", current)
        if not found:
            raise ValueError("releases/current.yaml at that commit has no " + CHART)
        version = found.group(1)
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", version) or version.startswith("0.0.0"):
        raise ValueError("invalid chart version: " + version)

    archive_name = CHART + "-" + version + ".tgz"
    archive = fetch(base + "repository/" + archive_name)
    digest = hashlib.sha256(archive).hexdigest()
    sums = fetch(base + "repository/SHA256SUMS").decode("utf-8")
    listed = re.search(r"(?m)^([0-9a-f]{64})\s+\*?" + re.escape(archive_name) + r"\s*$", sums)
    if not listed:
        raise ValueError(archive_name + " is not listed in repository/SHA256SUMS at that commit")
    if listed.group(1) != digest:
        raise ValueError("archive digest does not match repository/SHA256SUMS at that commit")
    chart_version, platform = chart_appversion(archive, CHART)
    if chart_version != version:
        raise ValueError("archive contains chart " + chart_version + ", expected " + version)

    pin = json.loads(PROFILE.read_text(encoding="utf-8"))
    pin["repository"] = base + "repository/"
    pin["version"] = version
    pin["sha256"] = digest
    pin["platformVersion"] = platform
    return pin


def version_key(version):
    """Order 1.0.0-dev.20 < 1.0.0-dev.21; a plain 1.0.0 sorts after its dev builds."""
    found = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-dev\.(\d+))?", version)
    if not found:
        raise ValueError("cannot order chart version: " + version)
    major, minor, patch, dev = found.groups()
    return (int(major), int(minor), int(patch), 1 if dev is None else 0, int(dev or 0))


def head_commit(run=None):
    """The 40-character commit at the head of oan-helm main (git ls-remote: no API token, no rate limit)."""
    run = run or (lambda cmd: subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
                                             universal_newlines=True).stdout)
    out = run(["git", "ls-remote", GIT, "refs/heads/main"])
    found = re.match(r"([0-9a-f]{40})\s+refs/heads/main\s*$", out.strip())
    if not found:
        raise ValueError("could not read the head of oan-helm main")
    return found.group(1)


def proposal(old, fetch=get, head=head_commit):
    """(new pin, reason) when oan-helm main has a newer Farmer chart than the pin, else (None, 'up to date ...')."""
    commit = head()
    new = new_pin(commit, None, fetch)
    if version_key(new["version"]) < version_key(old["version"]):
        raise ValueError("oan-helm main has chart %s, older than the pin %s: refusing to downgrade" % (new["version"], old["version"]))
    if new["version"] == old["version"] and new["sha256"] != old["sha256"]:
        raise ValueError("the archive for %s changed (%s -> %s): published archives are immutable, so stop and ask oan-helm"
                         % (old["version"], old["sha256"][:12], new["sha256"]))
    if new["version"] == old["version"]:
        return None, "up to date: chart %s is the newest Farmer chart on oan-helm main" % old["version"]
    return new, "newer chart %s released (pinned %s)" % (new["version"], old["version"])


def update_companions(old, new, root=None):
    """Nothing besides the pin is rewritten; the platform version is moved by hand (see the module notes)."""
    return []


def commit_of(pin):
    return pin["repository"].split("/oan-helm/")[1].split("/")[0]


def describe(old, new):
    """Old -> new lines for the console and the pull request."""
    rows = [("version", old.get("version"), new["version"]), ("sha256", old.get("sha256"), new["sha256"]),
            ("platformVersion", old.get("platformVersion"), new["platformVersion"]),
            ("commit", commit_of(old), commit_of(new))]
    return ["%-16s %s -> %s" % row for row in rows]


def apply_pin(old, new, root=None):
    """Write the pin and the files that must agree with it; returns the repository-relative paths changed."""
    PROFILE.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
    root = Path(root) if root else ROOT
    return [str(PROFILE.relative_to(root))] + update_companions(old, new, root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("commit", nargs="?", help="40-character oan-helm commit that contains the chart release")
    parser.add_argument("--latest", action="store_true", help="use the head of oan-helm main; stop if the chart is not newer")
    parser.add_argument("--version", help="chart version (default: releases/current.yaml at that commit)")
    parser.add_argument("--write", action="store_true", help="update ci/deploy/oan-chart.json")
    args = parser.parse_args(argv)
    old = json.loads(PROFILE.read_text(encoding="utf-8"))
    if args.latest:
        if args.commit or args.version:
            parser.error("--latest takes no commit or --version")
        new, reason = proposal(old)
        print(reason)
        if new is None:
            return 0
    else:
        if not args.commit:
            parser.error("give an oan-helm commit, or use --latest")
        new = new_pin(args.commit, args.version)
    print("\n".join(describe(old, new)))
    note = ("NOTE: the platform version changes: run scripts/bump-rp-version.sh and move REVIEWED_PLATFORMS in "
            "ci/deploy/oan_compat.py, ci/environments.py, ci/validation/native-release-contract.json and "
            "helm/environments/*/delivery.yaml by hand.")
    if not args.write:
        if old.get("platformVersion") != new["platformVersion"]:
            print(note)
        print("\n(dry run: nothing written; add --write to update " + str(PROFILE.name) + ")")
        return 0
    for path in apply_pin(old, new):
        print("updated " + path)
    if old.get("platformVersion") != new["platformVersion"]:
        print(note)
    print("next: python3 -m pytest -q test/unit/test_oan_chart.py test/unit/test_oan_compat.py")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, tarfile.TarError) as error:
        raise SystemExit("FAIL: " + str(error))
