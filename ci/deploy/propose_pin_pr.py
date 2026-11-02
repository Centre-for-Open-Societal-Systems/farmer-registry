"""Open a pull request that moves the pinned oan-helm chart, when oan-helm main differs from the pin.

Run by the last stage of the develop Jenkins build, after the deploy succeeded. It never deploys and
never changes `develop`: it pushes a branch and opens a pull request, and a person merges it.

  1. ci/deploy/bump_pin.py decides: a newer Farmer chart on oan-helm main (never a
     downgrade; a changed archive for the same version is an error). Nothing to do -> exit 0.
  2. Otherwise it writes the new pin on a new branch, checks the new archive with ci/deploy/oan_chart.py in the
     validation container (when VALIDATION_IMAGE is set) and runs the pin tests there, commits, pushes, opens
     the PR. A change of the platform version is not proposed (the images and oan_compat.py have to move with
     it): exit 5, reported, nothing pushed. The pull request build runs the whole unit suite again.
  3. The workspace is put back to the commit the build checked out.

Needs GH_TOKEN (a GitHub App installation token or a token) with Contents and Pull requests write on this
repository, only when a proposal is actually needed. Exit codes: 0 nothing to do or proposed (or already
proposed), 1 verification or git failed, 3 a proposal is needed but there is no token, 4 GitHub refused,
5 the new chart needs another platform version (a person moves it).

Standard library only; runs on the deploy node's stock Python (3.7 or later). The checks need Docker and the
`coss-ci/validation` image, which the deploy stage of the same build has built on this agent.
"""
import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = "develop"
AUTHOR = ["-c", "user.name=oan-ci", "-c", "user.email=oan-ci@users.noreply.github.com"]


class Refused(Exception):
    pass


def load_bump():
    spec = importlib.util.spec_from_file_location("bump_pin", HERE / "bump_pin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(cmd, label=None, cwd=None, env=None, check=True):
    """Run a command; the failure message names `label`, never the arguments (one carries the token)."""
    done = subprocess.run(cmd, cwd=str(cwd or ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    if check and done.returncode != 0:
        raise RuntimeError("%s failed (exit %d):\n%s" % (label or cmd[0], done.returncode, done.stdout[-1500:]))
    return done.stdout


def api(method, path, token, payload=None):
    request = urllib.request.Request("https://api.github.com" + path, method=method,
                                     data=json.dumps(payload).encode() if payload is not None else None)
    request.add_header("Authorization", "Bearer " + token)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
        except ValueError:
            body = {}
        return error.code, body


def slug_of(url):
    found = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url.strip())
    if not found:
        raise ValueError("origin is not a github.com repository: " + url.strip())
    return found.group(1)


def auth(token):
    basic = base64.b64encode(("x-access-token:" + token).encode()).decode()
    return ["-c", "http.extraheader=AUTHORIZATION: basic " + basic]


def pr_body(reason, lines):
    return "\n".join([
        "Moves the pinned oan-helm Farmer chart for the dev deploy (opened by the develop Jenkins build).",
        "",
        "```", reason] + lines + ["```", "",
        "Pinned to the head of oan-helm `main` at proposal time; the pin names that exact commit and is verified by SHA-256.",
        "",
        "**Merging this deploys to dev.** The develop build runs `ci/deploy/deploy-dev.sh`: archive checksum, schema, "
        "resource-preservation and render guards, then `helm upgrade --atomic`, which puts the previous revision back "
        "if the upgrade or its hooks fail.",
        "",
        "Before merging:",
        "- Read the oan-helm release notes for this chart (`git diff <old commit> <new commit> -- charts/openg2p-farmer-registry` "
        "in oan-helm).",
        "- Dev takes its values from the live release, so this PR changes only the chart archive, its SHA-256 and the "
        "commit it is downloaded from. The staging pin (`oan-chart-staging.json`) is not touched.",
        "- If the chart changes hooks, seed data or migrations, back up the Farmer registry and ID-generator databases "
        "first. A rollback restores the chart and values, not data.",
        "- The platform version is the same as today's, so the images and `oan_compat.py` are not affected.",
        ""])


def check_new_pin(bump, new, image, runner, root):
    """Verify the new archive and run the pin tests in the validation container (no network, repository read-only)."""
    if not image:
        print("VALIDATION_IMAGE is not set: the archive and pin tests are left to the pull request build.")
        return
    scratch = tempfile.mkdtemp()
    try:
        archive = Path(scratch) / "oan-farmer.tgz"
        archive.write_bytes(bump.get(bump.archive_url(new)))
        docker = ["docker", "run", "--rm", "--network", "none", "--user", "%d:%d" % (os.getuid(), os.getgid()),
                  "-v", "%s:/repo:ro" % root, "-v", "%s:/chart:ro" % scratch, image]
        runner(docker + ["python", "ci/deploy/oan_chart.py", "verify", "/chart/oan-farmer.tgz"],
               "verification of the new chart archive", root)
        runner(docker + ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                         "test/unit/test_oan_chart.py", "test/unit/test_oan_compat.py"], "the pin tests", root)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def propose(token, bump=None, runner=run, call=api, root=ROOT):
    bump = bump or load_bump()
    old = json.loads(bump.PROFILE.read_text(encoding="utf-8"))
    new, reason = bump.proposal(old)
    print(reason)
    if new is None:
        return 0
    lines = bump.describe(old, new)
    print("\n".join(lines))
    if new["platformVersion"] != old["platformVersion"]:
        print("The new chart needs platform %s (pinned: %s). Not proposed automatically: run scripts/bump-rp-version.sh, "
              "move REVIEWED_PLATFORMS in ci/deploy/oan_compat.py, ci/environments.py, ci/validation/native-release-contract.json "
              "and helm/environments/*/delivery.yaml, then python3 ci/deploy/bump_pin.py <commit> --write."
              % (new["platformVersion"], old["platformVersion"]))
        return 5
    if not token:
        print("A pin update is available but no GitHub credential was given (GH_TOKEN); nothing was proposed.")
        return 3

    branch = "bot/oan-chart-pin-%s-%s" % (new["version"], new["sha256"][:8])
    slug = slug_of(runner(["git", "remote", "get-url", "origin"], "git remote get-url", root))
    status, pulls = call("GET", "/repos/%s/pulls?state=all&head=%s:%s" % (slug, slug.split("/")[0], branch), token)
    if status != 200:
        print("GitHub refused to list pull requests (HTTP %s): the credential needs Contents and Pull requests "
              "write on %s." % (status, slug))
        return 4
    if pulls:
        print("Already proposed: %s (%s)" % (pulls[0].get("html_url"), pulls[0].get("state")))
        return 0

    title = "Pin OAN chart: " + reason
    body = pr_body(reason, lines)
    exists = runner(["git"] + auth(token) + ["ls-remote", "--heads", "origin", branch], "git ls-remote", root).strip()
    if not exists:
        original = runner(["git", "rev-parse", "HEAD"], "git rev-parse", root).strip()
        try:
            changed = bump.apply_pin(old, new, root)
            check_new_pin(bump, new, os.environ.get("VALIDATION_IMAGE", ""), runner, root)
            runner(["git", "checkout", "-q", "-b", branch], "git checkout -b", root)
            runner(["git", "add", "--"] + changed, "git add", root)
            runner(["git"] + AUTHOR + ["commit", "-q", "-m", title], "git commit", root)
            runner(["git"] + auth(token) + ["push", "-q", "origin", "HEAD:refs/heads/" + branch], "git push", root)
            print("pushed " + branch)
        finally:
            # leave the workspace as the build found it
            runner(["git", "checkout", "-q", "-f", original], "git checkout", root, check=False)
            runner(["git", "branch", "-D", branch], "git branch -D", root, check=False)
    status, created = call("POST", "/repos/%s/pulls" % slug, token,
                           {"title": title, "head": branch, "base": BASE, "body": body})
    if status not in (200, 201):
        print("GitHub refused to create the pull request (HTTP %s): %s. The branch %s is pushed; open the pull request "
              "from it by hand, or give the credential Pull requests write." % (status, (created or {}).get("message"), branch))
        return 4
    print("opened " + created.get("html_url", "(no url)"))
    return 0


def main():
    try:
        return propose(os.environ.get("GH_TOKEN", ""))
    except (ValueError, KeyError, OSError) as error:
        print("FAIL: %s" % error)
        return 1
    except RuntimeError as error:
        print("FAIL: %s" % error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
