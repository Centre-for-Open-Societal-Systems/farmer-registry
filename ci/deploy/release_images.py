"""After a successful deploy: put this build's images into the oan-helm Farmer registry chart through a pull request.

Run by the stage "Open oan-helm image PR" of every develop build, after the images were pushed to ECR and deployed to
New Dev (a failed deploy fails the build, and then this stage does not run). It does not wait for the pull request to be
merged: the stage, and the build, are a success once the pull request is open.

  1. Read the ECR digests of the build (service-outcomes/registry-images.tsv, written by the Publish stage:
     component<TAB>image<TAB>sha256:...).
  2. Rewrite the image tags in charts/openg2p-farmer-registry/values.yaml of oan-helm to <commit12>@sha256:<digest>
     for staffUi, staffApi, partnerApi, celeryWorker, celeryBeat, dbSeed and sanity. Only those lines change; the file is
     edited as text. The analytics/dashboard images are separate services and are not touched.
  3. Put that change on the branch bot/farmer-images-<commit12> of the FORK of oan-helm (GH_USER/oan-helm), created from
     the current head of the org repo's main, and open a pull request from it into
     Centre-for-Open-Societal-Systems/oan-helm main (or update the open one for the same commit).

A person with write access reviews and merges that pull request. oan-helm's release workflow then publishes the next
chart version and writes the CHANGELOG entry. Nothing here touches the cluster; the chart pin of this repository
is moved by hand with ci/deploy/bump_pin.py.

A commit whose images oan-helm main already carries is left alone (a re-run, Replay or rebuild would only give new digests
for the same tag): one pull request per commit merged to develop. The commit that merges a chart-pin pull request (it
changes only ci/deploy/oan-chart.json) gets none either, which keeps the pin and image pull requests from chasing each
other.

Needs GH_USER (the account that owns the fork) and GH_TOKEN (a classic token of that account with the public_repo scope;
the oan-helm repository is public, so any account can open a pull request from its fork). OAN_HELM_FORK is the name of the
fork (default oan-helm). DRY_RUN=1 prints the change and touches nothing.

Exit codes: 0 pull request open (or nothing to do), 1 unexpected failure, 3 no credential, 4 GitHub refused.

Standard library only; runs on the deploy node's stock Python (3.7 or later).
"""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SLUG = "Centre-for-Open-Societal-Systems/oan-helm"
CHART = "openg2p-farmer-registry"
VALUES_PATH = "charts/%s/values.yaml" % CHART
DIGESTS = "service-outcomes/registry-images.tsv"
PR_FILE = "service-outcomes/oan-helm-pr.txt"
# chart values section under `registry:` -> ECR component (one repository per component: <registry>/<repository>/<component>)
REGISTRY = (("staffUi", "staff-ui"), ("staffApi", "staff-api"), ("partnerApi", "partner-api"), ("celeryWorker", "celery"),
            ("celeryBeat", "celery"), ("dbSeed", "db-seed"), ("sanity", "sanity-tests"))
# A commit that changes only these files is the merge of a chart-pin pull request. It is not left
# without an image pull request by accident: the pin follows an oan-helm release, and a release follows an image pull
# request, so recording images for the pin commit too would start the cycle again, one commit per lap.
PIN_ONLY_FILES = frozenset(["ci/deploy/oan-chart.json"])
COMPONENTS = sorted(set(component for _, component in REGISTRY))


class Stop(Exception):
    """A reason to stop with an exit code and a message for the build log."""

    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code


# ---- the values file ---------------------------------------------------------------------------------------------

def read_digests(text, registry=None, repository=None, image_tag=None):
    """{component: 'sha256:..'} from component<TAB>image<TAB>digest lines.

    With `registry`, `repository` and `image_tag` the image column must be exactly <registry>/<repository>/<component>:<tag>.
    """
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 3 or not re.fullmatch(r"sha256:[0-9a-f]{64}", parts[2].strip()):
            raise ValueError("bad digest line: " + line[:80])
        component, image = parts[0].strip(), parts[1].strip()
        if registry and image != "%s/%s/%s:%s" % (registry, repository, component, image_tag):
            raise ValueError("the pushed image of %s is %s, not the image of build %s" % (component, image, image_tag))
        result[component] = parts[2].strip()
    return result


def wanted(image_tag, digests):
    """{values section: 'commit@sha256:..'} for the registry components."""
    if not re.fullmatch(r"[0-9a-f]{12}", image_tag):
        raise ValueError("IMAGE_TAG must be the 12-character commit tag")
    missing = sorted(set(COMPONENTS) - set(digests))
    if missing:
        raise ValueError("no ECR digest for: " + ", ".join(missing))
    return dict((section, "%s@%s" % (image_tag, digests[component])) for section, component in REGISTRY)


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _block_end(lines, start, indent):
    """Index after the block that starts at `start`: the next non-blank line indented `indent` or less."""
    index = start + 1
    # Blank lines and comment lines (whatever their column) belong to the block they are in.
    while index < len(lines) and (not lines[index].strip() or lines[index].lstrip().startswith("#")
                                  or _indent(lines[index]) > indent):
        index += 1
    return index


def _find(lines, pattern, start, end):
    for index in range(start, end):
        if re.fullmatch(pattern, lines[index]):
            return index
    raise ValueError("values.yaml has no line matching %r" % pattern)


def _set_value(lines, start, end, key, value, indent):
    """Replace `<indent>key: ...` inside lines[start:end]."""
    found = _find(lines, r" {%d}%s: \S.*" % (indent, key), start, end)
    lines[found] = "%s%s: %s" % (" " * indent, key, value)


def expected_repositories(registry, path):
    return dict((section, "%s/%s/%s" % (registry, path, component)) for section, component in REGISTRY)


def rewrite_values(text, registry_tags, repositories=None):
    """The values text with the new image tags; everything else is byte for byte as it was.

    `repositories` ({section: expected repository}) makes the rewrite refuse an image block whose repository is not the
    expected ECR repository.
    """
    lines = text.split("\n")
    top = _find(lines, r"registry:\s*", 0, len(lines))
    top_end = _block_end(lines, top, 0)
    for section, tag in registry_tags.items():
        header = _find(lines, r" {2}%s:\s*" % section, top + 1, top_end)
        end = _block_end(lines, header, 2)
        image = _find(lines, r" {4}image:\s*", header + 1, end)
        image_end = _block_end(lines, image, 4)
        if repositories and section in repositories:
            repo = lines[_find(lines, r" {6}repository: \S+", image + 1, image_end)].split(": ", 1)[1].strip()
            if repo != repositories[section]:
                raise ValueError("%s image repository is %s, expected %s" % (section, repo, repositories[section]))
        _set_value(lines, image + 1, image_end, "tag", tag, 6)
    return "\n".join(lines)


def released_before(text, image_tag):
    """True when the values already carry this commit's images (an earlier build of the same commit released them)."""
    return re.search(r"(?m)^\s+tag: %s@sha256:[0-9a-f]{64}\s*$" % re.escape(image_tag), text) is not None


def changed_files(root, env):
    """Files the built commit changed against its first parent (CHANGED_FILES, newline separated, overrides it)."""
    if "CHANGED_FILES" in env:
        return [line.strip() for line in env["CHANGED_FILES"].splitlines() if line.strip()]
    try:
        out = subprocess.run(["git", "diff", "--name-only", "HEAD^1", "HEAD"], cwd=str(root), stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, universal_newlines=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None                                    # a first commit, or no git: assume the commit carries code
    return [line.strip() for line in out.splitlines() if line.strip()]


# ---- GitHub ------------------------------------------------------------------------------------------------------

def api(method, path, token, payload=None):
    request = urllib.request.Request("https://api.github.com" + path, method=method,
                                     data=json.dumps(payload).encode() if payload is not None else None)
    request.add_header("Authorization", "Bearer " + token)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return response.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
        except ValueError:
            body = {}
        return error.code, body


def refused(status, body, doing, repo=SLUG):
    message = (body or {}).get("message", "")
    if status in (401, 403, 404):
        raise Stop(4, "GitHub refused to %s on %s (HTTP %s: %s). The token needs the public_repo scope (classic token of the "
                      "account that owns the fork), and the fork must exist." % (doing, repo, status, message))
    raise Stop(1, "GitHub could not %s on %s (HTTP %s: %s)" % (doing, repo, status, message))


class Proposal(object):
    """Opens (or updates) the pull request from the fork's branch into oan-helm main."""

    def __init__(self, token, owner, fork_name="oan-helm", call=api, out=print):
        self.token, self.owner, self.call, self.out = token, owner, call, out
        self.fork = "%s/%s" % (owner, fork_name)
        self.note = None

    def upstream(self, method, path, payload=None):
        return self.call(method, "/repos/%s%s" % (SLUG, path), self.token, payload)

    def mine(self, method, path, payload=None):
        return self.call(method, "/repos/%s%s" % (self.fork, path), self.token, payload)

    # -- steps
    def main_head(self):
        status, body = self.upstream("GET", "/git/ref/heads/main")
        if status != 200:
            refused(status, body, "read oan-helm main")
        return body["object"]["sha"]

    def contents(self, repo_call, ref, repo):
        status, body = repo_call("GET", "/contents/%s?ref=%s" % (VALUES_PATH, ref))
        if status != 200:
            refused(status, body, "read " + VALUES_PATH, repo)
        return base64.b64decode(body["content"]).decode("utf-8"), body["sha"]

    def prepare_branch(self, branch, main_sha):
        """The fork's branch starts from the head of the org repo's main (created, or reset when it is left over)."""
        status, body = self.mine("POST", "/git/refs", {"ref": "refs/heads/" + branch, "sha": main_sha})
        if status in (200, 201):
            return
        message = str((body or {}).get("message", ""))
        if status == 422 and "already exists" in message:
            status, body = self.mine("PATCH", "/git/refs/heads/" + branch, {"sha": main_sha, "force": True})
            if status != 200:
                refused(status, body, "reset the branch " + branch, self.fork)
            return
        if status in (404, 422):
            # The fork cannot see that commit yet: bring the fork's main up to date with the org repo, then try again.
            self.out("The fork does not have oan-helm commit %s yet; syncing its main." % main_sha[:12])
            sync_status, sync_body = self.mine("POST", "/merge-upstream", {"branch": "main"})
            if sync_status not in (200, 201):
                raise Stop(4, "The fork %s cannot be brought up to date with %s (HTTP %s: %s). Use 'Sync fork' on GitHub, "
                              "then rerun the build." % (self.fork, SLUG, sync_status, (sync_body or {}).get("message", "")))
            status, body = self.mine("POST", "/git/refs", {"ref": "refs/heads/" + branch, "sha": main_sha})
            if status in (200, 201):
                return
            if status == 422 and "already exists" in str((body or {}).get("message", "")):
                status, body = self.mine("PATCH", "/git/refs/heads/" + branch, {"sha": main_sha, "force": True})
                if status == 200:
                    return
        refused(status, body, "create the branch " + branch, self.fork)

    def commit_values(self, branch, new_text, message):
        text, blob = self.contents(self.mine, branch, self.fork)
        if text != new_text:
            status, body = self.mine("PUT", "/contents/" + VALUES_PATH, {
                "message": message, "branch": branch, "sha": blob,
                "content": base64.b64encode(new_text.encode("utf-8")).decode("ascii")})
            if status not in (200, 201):
                refused(status, body, "commit the new image tags", self.fork)

    def open_pull_request(self, branch, title, body_text):
        head = "%s:%s" % (self.owner, branch)
        status, pulls = self.upstream("GET", "/pulls?state=open&head=%s" % head)
        if status != 200:
            refused(status, pulls, "list pull requests")
        if pulls:
            number = pulls[0]["number"]
            status, body = self.upstream("PATCH", "/pulls/%d" % number, {"title": title, "body": body_text})
            if status != 200:
                refused(status, body, "update the pull request")
            return pulls[0]["html_url"], False
        status, created = self.upstream("POST", "/pulls", {"title": title, "head": head, "base": "main",
                                                           "body": body_text, "maintainer_can_modify": True})
        if status not in (200, 201):
            refused(status, created, "open the pull request")
        return created["html_url"], True

    # -- the whole stage
    def run(self, env, root, digests_text):
        image_tag = env["IMAGE_TAG"]
        path = env.get("ECR_REPOSITORY", "openg2p/farmer-registry")
        tags = wanted(image_tag, read_digests(digests_text, env["ECR_REGISTRY"], path, image_tag))
        repositories = expected_repositories(env["ECR_REGISTRY"], path)
        main_sha = self.main_head()
        text, _ = self.contents(self.upstream, "main", SLUG)
        new_text = rewrite_values(text, tags, repositories)
        subject = env.get("COMMIT_SUBJECT", "").strip()[:100]
        self.out("images of build %s:" % image_tag)
        for section, tag in sorted(tags.items()):
            self.out("  %-13s %s" % (section, tag))
        files = changed_files(root, env)
        if files and set(files) <= PIN_ONLY_FILES:
            self.note = ("Commit %s only moves the chart pin (%s): no image pull request, or every pin merge would start "
                         "another round." % (image_tag, ", ".join(sorted(files))))
            self.out(self.note)
            return None
        if released_before(text, image_tag):
            self.note = ("Commit %s is already in oan-helm main: a re-run or rebuild of the same commit opens no new pull "
                         "request." % image_tag)
            self.out(self.note)
            return None
        if env.get("DRY_RUN"):
            self.out("DRY_RUN: %s would change on %s." % (VALUES_PATH, SLUG))
            return None
        branch = "bot/farmer-images-" + image_tag
        title = "Farmer registry images %s%s" % (image_tag, (": " + subject) if subject else "")
        body = "\n".join([
            "Image tags and digests of Farmer Registry develop build `%s` (source commit `%s`)." % (
                image_tag, env.get("SOURCE_COMMIT", image_tag)),
            "", "Jenkins build: %s" % env.get("BUILD_URL", "(unknown)"), "",
            "Opened by the develop Jenkins build of farmer-registry after it pushed these images to ECR and deployed them to "
            "New Dev successfully. Only the image `tag` lines of the registry components in `%s` change. Merging releases "
            "the next `%s` chart." % (VALUES_PATH, CHART), ""])
        self.prepare_branch(branch, main_sha)
        self.commit_values(branch, new_text, title)
        url, created = self.open_pull_request(branch, title, body)
        self.out(("pull request opened: " if created else "pull request updated: ") + url)
        return url


def main(env=None, root=ROOT, call=api):
    env = dict(os.environ if env is None else env)
    root = Path(root)
    try:
        for name in ("IMAGE_TAG", "ECR_REGISTRY"):
            if not env.get(name):
                raise Stop(1, name + " is not set")
        dry = bool(env.get("DRY_RUN"))
        if not dry and not (env.get("GH_TOKEN") and env.get("GH_USER")):
            raise Stop(3, "No GitHub credential (GH_USER = the account that owns the oan-helm fork, GH_TOKEN = its token): "
                          "no pull request was opened.")
        digests = (root / DIGESTS).read_text(encoding="utf-8")
        proposal = Proposal(env.get("GH_TOKEN", ""), env.get("GH_USER", "dry-run"), env.get("OAN_HELM_FORK", "oan-helm"),
                            call=call)
        url = proposal.run(env, root, digests)
        if url:
            target = root / PR_FILE
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(url + "\n", encoding="utf-8")
        return 0
    except Stop as stop:
        print("FAIL: %s" % stop)
        return stop.code
    except (ValueError, KeyError, OSError) as error:
        print("FAIL: %s: %s" % (error.__class__.__name__, error))
        return 1


if __name__ == "__main__":
    sys.exit(main())
