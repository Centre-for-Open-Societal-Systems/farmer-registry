"""The oan-helm image pull request (ci/deploy/release_images.py) and its stage, with a stand-in GitHub.

No network, no cluster. release_images.py is standard library only because it runs on the Jenkins deploy node's stock
Python (3.7); this file runs in the validation container.
"""
import base64
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load_release():
    spec = importlib.util.spec_from_file_location("release_images_under_test", ROOT / "ci/deploy/release_images.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REG = "123456789012.dkr.ecr.ap-south-1.amazonaws.com"
PATH_ = "openg2p/farmer-registry"
OLD_TAG = "bf78e69a5fd6"
NEW_TAG = "0123456789ab"
COMPONENTS = ["staff-ui", "staff-api", "partner-api", "celery", "db-seed", "sanity-tests"]


def sample_values(tag=OLD_TAG):
    """The shape of charts/openg2p-farmer-registry/values.yaml in oan-helm, reduced."""
    old = "e" * 64

    def img(component):
        return "    image:\n      repository: %s/%s/%s\n      tag: %s@sha256:%s\n" % (REG, PATH_, component, tag, old)
    return (
        "global:\n  baseDomain: development.oanstaging.com\n"
        "registry:\n"
        "  staffUi:\n" + img("staff-ui") + "    iamPublicUrl: 'https://x'\n"
        "# a comment at column 0 inside the registry block\n"
        "  staffApi:\n" + img("staff-api") + "    envVars:\n      A: 'b'\n"
        "  partnerApi:\n" + img("partner-api") +
        "  celeryWorker:\n" + img("celery") +
        "  celeryBeat:\n" + img("celery") +
        "  dbSeed:\n" + img("db-seed") + "    loadSampleData: false\n"
        "  keycloak-init:\n    image:\n      repository: docker.io/x/y\n      tag: 1.0.0\n"
        "  sanity:\n    enabled: true\n" + img("sanity-tests") + "    regType: Farmer\n"
        "analytics:\n  image:\n    repository: ''\n    tag: ''\n"
        "dashboardApi:\n  image:\n    digest: sha256:%s\n    repository: %s/%s/dashboard-api\n    tag: 85fd0a3c2518\n" % (old, REG, PATH_))


def release_digests():
    return dict((c, "sha256:" + ("%x" % (i + 1)) * 64) for i, c in enumerate(COMPONENTS))


def tsv(tag=NEW_TAG, digests=None):
    """service-outcomes/registry-images.tsv as the Publish stage writes it: component, image, digest."""
    digests = digests or release_digests()
    return "".join("%s\t%s/%s/%s:%s\t%s\n" % (c, REG, PATH_, c, tag, d) for c, d in digests.items())


class ImageValuesTests(unittest.TestCase):
    def setUp(self):
        self.r = load_release()
        self.tags = self.r.wanted(NEW_TAG, self.r.read_digests(tsv()))
        self.repos = self.r.expected_repositories(REG, PATH_)

    def test_only_the_seven_image_tag_lines_change(self):
        old = sample_values()
        new = self.r.rewrite_values(old, self.tags, self.repos)
        changed = [(a, b) for a, b in zip(old.split("\n"), new.split("\n")) if a != b]
        self.assertEqual(len(old.split("\n")), len(new.split("\n")))
        self.assertEqual(len(changed), 7)                          # staffUi, staffApi, partnerApi, worker, beat, dbSeed, sanity
        self.assertTrue(all(b.lstrip().startswith("tag:") for _, b in changed))
        self.assertIn("      tag: %s@%s" % (NEW_TAG, release_digests()["staff-api"]), new)
        # untouched: the comment, the init image, the analytics and dashboard images
        for kept in ("# a comment at column 0 inside the registry block", "tag: 1.0.0", "    tag: ''", "tag: 85fd0a3c2518",
                     "      A: 'b'"):
            self.assertIn(kept, new)

    def test_both_celery_workloads_get_the_celery_digest(self):
        new = self.r.rewrite_values(sample_values(), self.tags, self.repos)
        self.assertEqual(new.count("%s@%s" % (NEW_TAG, release_digests()["celery"])), 2)

    def test_rewriting_twice_changes_nothing(self):
        once = self.r.rewrite_values(sample_values(), self.tags, self.repos)
        self.assertEqual(self.r.rewrite_values(once, self.tags, self.repos), once)
        self.assertTrue(self.r.released_before(once, NEW_TAG))
        self.assertFalse(self.r.released_before(sample_values(), NEW_TAG))

    def test_the_tags_stay_strings_for_yaml(self):
        import yaml
        for tag in ("875427410733", "123456e78901"):
            tags = self.r.wanted(tag, self.r.read_digests(tsv(tag)))
            document = yaml.safe_load(self.r.rewrite_values(sample_values(), tags, self.repos))
            self.assertIsInstance(document["registry"]["staffApi"]["image"]["tag"], str)

    def test_another_ecr_repository_is_refused(self):
        bad = sample_values().replace("/staff-api", "/someone-elses-api")
        with self.assertRaisesRegex(ValueError, "staffApi image repository"):
            self.r.rewrite_values(bad, self.tags, self.repos)

    def test_a_missing_section_is_an_error_not_a_silent_skip(self):
        with self.assertRaises(ValueError):
            self.r.rewrite_values(sample_values().replace("  dbSeed:", "  dbSeedX:"), self.tags, self.repos)

    def test_digest_lines_are_read_and_validated(self):
        self.assertEqual(self.r.read_digests(tsv()), release_digests())
        self.assertEqual(self.r.read_digests(tsv(), REG, PATH_, NEW_TAG), release_digests())
        for bad in ("staff-api\tx\tlatest\n", "staff-api\tsha256:" + "a" * 64 + "\n"):
            with self.assertRaises(ValueError):
                self.r.read_digests(bad)
        with self.assertRaisesRegex(ValueError, "not the image of build"):        # a stale file from another build
            self.r.read_digests(tsv("ffffffffffff"), REG, PATH_, NEW_TAG)

    def test_every_component_needs_a_digest_and_the_tag_a_commit(self):
        partial = dict(release_digests())
        del partial["sanity-tests"]
        with self.assertRaisesRegex(ValueError, "sanity-tests"):
            self.r.wanted(NEW_TAG, partial)
        with self.assertRaises(ValueError):
            self.r.wanted("latest", release_digests())


FORK = "fork-owner/oan-helm"


class FakeGitHub(object):
    """oan-helm as the stage sees it: the org repo (main, pull requests) and the fork (branch, commit)."""

    def __init__(self, release):
        self.r = release
        self.main_sha = "a" * 40
        self.text = sample_values()                 # values.yaml on the org repo's main
        self.branches = {}                          # fork branch -> text
        self.knows_commit = True                    # False: the fork cannot see main's head until it is synced
        self.pulls = []                             # open pull requests on the org repo
        self.calls = []
        self.refuse = {}                            # (method, path-prefix) -> status
        self.synced = False

    def __call__(self, method, path, token, payload=None):
        self.calls.append((method, path, payload))
        for (m, prefix), status in self.refuse.items():
            if method == m and prefix in path:
                return status, {"message": "refused"}
        org, fork = "/repos/%s" % self.r.SLUG, "/repos/%s" % FORK
        if path.startswith(org):
            rest = path[len(org):]
            if method == "GET" and rest == "/git/ref/heads/main":
                return 200, {"object": {"sha": self.main_sha}}
            if method == "GET" and rest.startswith("/contents/") and rest.endswith("?ref=main"):
                return 200, {"content": base64.b64encode(self.text.encode()).decode(), "sha": "blob1"}
            if method == "GET" and rest.startswith("/pulls?"):
                return 200, list(self.pulls)
            if method == "POST" and rest == "/pulls":
                pull = {"number": 11, "html_url": "https://github.com/%s/pull/11" % self.r.SLUG, "payload": payload}
                self.pulls.append(pull)
                return 201, pull
            if method == "PATCH" and rest.startswith("/pulls/"):
                self.pulls[0]["payload"] = payload
                return 200, {}
        elif path.startswith(fork):
            rest = path[len(fork):]
            if method == "POST" and rest == "/merge-upstream":
                self.synced = self.knows_commit = True
                return 200, {}
            if method == "POST" and rest == "/git/refs":
                name = payload["ref"][len("refs/heads/"):]
                if name in self.branches:
                    return 422, {"message": "Reference already exists"}
                if not self.knows_commit:
                    return 422, {"message": "Object does not exist"}
                self.branches[name] = self.text
                return 201, {}
            if method == "PATCH" and rest.startswith("/git/refs/heads/"):
                self.branches[rest[len("/git/refs/heads/"):]] = self.text
                return 200, {}
            if method == "GET" and rest.startswith("/contents/"):
                return 200, {"content": base64.b64encode(self.branches[rest.split("?ref=")[1]].encode()).decode(), "sha": "blob1"}
            if method == "PUT" and rest.startswith("/contents/"):
                self.branches[payload["branch"]] = base64.b64decode(payload["content"]).decode()
                return 200, {}
        raise AssertionError("unexpected call %s %s" % (method, path))


BRANCH = "bot/farmer-images-" + NEW_TAG


class ImagePullRequestTests(unittest.TestCase):
    """ci/deploy/release_images.py opens the pull request and stops."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "service-outcomes").mkdir()
        (self.root / "service-outcomes/registry-images.tsv").write_text(tsv())
        self.r = load_release()
        self.gh = FakeGitHub(self.r)
        self.out = []
        self.env = {"IMAGE_TAG": NEW_TAG, "ECR_REGISTRY": REG, "ECR_REPOSITORY": PATH_, "COMMIT_SUBJECT": "Add a field",
                    "SOURCE_COMMIT": NEW_TAG + "f" * 28, "BUILD_URL": "https://jenkins/job/7/"}
        self.tags = self.r.wanted(NEW_TAG, self.r.read_digests(tsv()))

    def proposal(self):
        return self.r.Proposal("tok", "fork-owner", "oan-helm", call=self.gh, out=self.out.append)

    def run_stage(self, **overrides):
        env = dict(self.env, **overrides)
        return self.proposal().run(env, self.root, (self.root / "service-outcomes/registry-images.tsv").read_text())

    def methods(self):
        return [(m, p.split("?")[0].replace("/repos/%s" % self.r.SLUG, "ORG").replace("/repos/%s" % FORK, "FORK"))
                for m, p, _ in self.gh.calls]

    def test_the_branch_goes_to_the_fork_and_the_pull_request_to_the_org_main(self):
        url = self.run_stage()
        self.assertEqual(url, "https://github.com/%s/pull/11" % self.r.SLUG)
        calls = self.methods()
        order = [("POST", "FORK/git/refs"), ("PUT", "FORK/contents/charts/openg2p-farmer-registry/values.yaml"),
                 ("POST", "ORG/pulls")]
        positions = [calls.index(c) for c in order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("tag: %s@%s" % (NEW_TAG, release_digests()["staff-api"]), self.gh.branches[BRANCH])
        _, _, body = next(c for c in self.gh.calls if c[0] == "POST" and c[1].endswith("/pulls"))
        self.assertEqual((body["base"], body["head"]), ("main", "fork-owner:" + BRANCH))
        self.assertIn("Farmer registry images %s: Add a field" % NEW_TAG, body["title"])
        self.assertIn("https://jenkins/job/7/", body["body"])
        # nothing in the org repo is written, merged or waited for
        self.assertEqual([m for m, p in calls if p.startswith("ORG") and m not in ("GET", "POST")], [])
        self.assertFalse([c for c in calls if "merge" in c[1] and "merge-upstream" not in c[1] or "check-runs" in c[1]])

    def test_only_the_image_lines_of_the_chart_are_changed_on_the_branch(self):
        self.run_stage()
        old = sample_values().split("\n")
        new = self.gh.branches[BRANCH].split("\n")
        changed = [b for a, b in zip(old, new) if a != b]
        self.assertEqual(len(old), len(new))
        self.assertEqual(len(changed), 7)
        self.assertTrue(all(c.lstrip().startswith("tag:") for c in changed))

    def test_a_commit_that_oan_helm_main_already_carries_opens_nothing(self):
        self.gh.text = self.r.rewrite_values(sample_values(), self.tags)
        proposal = self.proposal()
        self.assertIsNone(proposal.run(dict(self.env), self.root, (self.root / "service-outcomes/registry-images.tsv").read_text()))
        calls = self.methods()
        self.assertNotIn(("POST", "ORG/pulls"), calls)
        self.assertNotIn(("POST", "FORK/git/refs"), calls)
        self.assertIn("already in oan-helm main", proposal.note)

    def test_the_commit_that_merges_a_chart_pin_pull_request_opens_nothing(self):
        proposal = self.proposal()
        for files in ("ci/deploy/oan-chart.json\n", "ci/deploy/oan-chart.json"):
            self.assertIsNone(proposal.run(dict(self.env, CHANGED_FILES=files), self.root,
                                           (self.root / "service-outcomes/registry-images.tsv").read_text()))
            self.assertIn("only moves the chart pin", proposal.note)
        self.assertNotIn(("POST", "ORG/pulls"), self.methods())
        self.assertNotIn(("POST", "FORK/git/refs"), self.methods())

    def test_a_commit_with_code_or_a_pin_plus_anything_else_gets_its_pull_request(self):
        for files in ("ci/deploy/oan-chart.json\ndocker/staff-api/Dockerfile\n", "Jenkinsfile\n", ""):
            self.gh.branches.clear()
            self.gh.pulls.clear()
            self.assertTrue(self.run_stage(CHANGED_FILES=files), files)

    def test_the_changed_files_are_read_from_git_when_not_given(self):
        subprocess.run("git init -q . && git config user.email a@b && git config user.name n && mkdir -p ci/deploy"
                       " && echo 1 > ci/deploy/oan-chart.json && echo 1 > x && git add . && git commit -qm one"
                       " && echo 2 > ci/deploy/oan-chart.json && git commit -qam two", shell=True, cwd=str(self.root), check=True)
        self.assertEqual(self.r.changed_files(self.root, {}), ["ci/deploy/oan-chart.json"])
        self.assertIsNone(self.run_stage_in(self.root))

    def run_stage_in(self, root):
        return self.proposal().run(dict(self.env), root, (root / "service-outcomes/registry-images.tsv").read_text())

    def test_a_rebuild_with_new_digests_for_the_same_commit_is_still_skipped(self):
        other = self.r.read_digests(tsv(digests=dict(release_digests(), **{"staff-api": "sha256:" + "9" * 64})))
        self.gh.text = self.r.rewrite_values(sample_values(), self.r.wanted(NEW_TAG, other))
        self.assertIsNone(self.run_stage())
        self.assertNotIn(("POST", "ORG/pulls"), self.methods())

    def test_the_next_commit_gets_its_own_pull_request(self):
        self.gh.text = self.r.rewrite_values(sample_values(), self.tags)    # the previous commit is merged
        (self.root / "service-outcomes/registry-images.tsv").write_text(tsv("fedcba987654"))
        url = self.run_stage(IMAGE_TAG="fedcba987654")
        self.assertTrue(url)
        self.assertIn("tag: fedcba987654@", self.gh.branches["bot/farmer-images-fedcba987654"])

    def test_a_left_over_branch_is_reset_and_the_open_pull_request_is_updated_not_duplicated(self):
        self.gh.branches[BRANCH] = "stale"
        self.gh.pulls.append({"number": 5, "html_url": "https://github.com/%s/pull/5" % self.r.SLUG, "payload": {}})
        url = self.run_stage()
        self.assertEqual(url, "https://github.com/%s/pull/5" % self.r.SLUG)
        calls = self.methods()
        self.assertIn(("PATCH", "FORK/git/refs/heads/" + BRANCH), calls)
        self.assertIn(("PATCH", "ORG/pulls/5"), calls)
        self.assertNotIn(("POST", "ORG/pulls"), calls)
        self.assertIn(NEW_TAG, self.gh.branches[BRANCH])

    def test_a_fork_that_has_not_seen_main_yet_is_synced_first(self):
        self.gh.knows_commit = False
        self.run_stage()
        self.assertTrue(self.gh.synced)
        self.assertIn(("POST", "ORG/pulls"), self.methods())
        self.assertIn("syncing", "\n".join(self.out))

    def test_a_fork_that_cannot_be_synced_is_reported(self):
        self.gh.knows_commit = False
        self.gh.refuse[("POST", "/merge-upstream")] = 409
        with self.assertRaises(self.r.Stop) as caught:
            self.run_stage()
        self.assertEqual(caught.exception.code, 4)
        self.assertIn("Sync fork", str(caught.exception))

    def test_a_token_without_access_is_reported_as_such(self):
        self.gh.refuse[("POST", "/git/refs")] = 403
        with self.assertRaises(self.r.Stop) as caught:
            self.run_stage()
        self.assertEqual(caught.exception.code, 4)
        self.assertIn("public_repo", str(caught.exception))
        self.assertNotIn("tok", str(caught.exception).replace("token", ""))

    def test_refused_pull_request_is_reported(self):
        self.gh.refuse[("POST", "/pulls")] = 403
        with self.assertRaises(self.r.Stop) as caught:
            self.run_stage()
        self.assertEqual(caught.exception.code, 4)

    def test_dry_run_changes_nothing(self):
        self.assertIsNone(self.run_stage(DRY_RUN="1"))
        self.assertEqual([m for m, _ in self.methods() if m != "GET"], [])

    def test_main_writes_the_pull_request_url_and_nothing_else(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.r.main(env=dict(self.env, GH_TOKEN="tok", GH_USER="fork-owner"), root=self.root, call=self.gh)
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual((self.root / "service-outcomes/oan-helm-pr.txt").read_text().strip(), "https://github.com/%s/pull/11" % self.r.SLUG)
        self.assertNotIn("tok", out.getvalue().replace("token", ""))

    def test_main_without_a_credential_is_exit_3_and_opens_nothing(self):
        for env in (dict(self.env), dict(self.env, GH_TOKEN="tok"), dict(self.env, GH_USER="fork-owner")):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = self.r.main(env=env, root=self.root, call=self.gh)
            self.assertEqual(code, 3)
        self.assertEqual(self.gh.calls, [])
        self.assertFalse((self.root / "service-outcomes/oan-helm-pr.txt").exists())

    def test_main_leaves_no_pull_request_file_when_the_commit_was_already_taken(self):
        self.gh.text = self.r.rewrite_values(sample_values(), self.tags)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.r.main(env=dict(self.env, GH_TOKEN="tok", GH_USER="fork-owner"), root=self.root, call=self.gh)
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "service-outcomes/oan-helm-pr.txt").exists())


class PipelineWiringTests(unittest.TestCase):
    """ci/pipelines/dev.groovy: ... deploy (atomic rollback) -> pin pull request -> oan-helm image pull request, last."""

    def setUp(self):
        self.text = (ROOT / "ci/pipelines/dev.groovy").read_text()

    def stage(self):
        return self.text.split("stage('Open oan-helm image PR')", 1)[1].split("\n    post {", 1)[0]

    def test_the_image_pull_request_is_the_last_stage_after_deploy_and_pin(self):
        order = [self.text.index("stage('%s')" % n) for n in
                 ("Publish", "Deploy (registry)", "Propose chart pin update", "Open oan-helm image PR")]
        self.assertEqual(order, sorted(order))
        self.assertLess(self.text.index("stage('Open oan-helm image PR')"), self.text.index("\n    post {"))

    def test_the_digests_the_publish_stage_wrote_are_stashed_for_it(self):
        publish = self.text.split("stage('Publish')", 1)[1].split("stage('Deploy (package)')", 1)[0]
        self.assertIn("service-outcomes/registry-images.tsv", publish)
        self.assertLess(publish.index("registry-images.tsv\n"), publish.index("stash name: 'image-digests'"))
        self.assertIn("includes: 'service-outcomes/registry-images.tsv'", publish)
        self.assertIn("unstash 'image-digests'", self.stage())

    def test_the_stage_cannot_fail_the_build_and_runs_only_for_a_normal_develop_deploy(self):
        stage = self.stage()
        self.assertIn("catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE')", stage)
        self.assertIn("python3 ci/deploy/release_images.py", stage)
        self.assertIn("branch 'develop'", stage)
        self.assertIn("not { changeRequest() }", stage)
        self.assertIn("env.DELIVERY_ACTION == 'deploy'", stage)          # not after a fresh install
        self.assertIn("agent { label 'vpn-agent2' }", stage)
        self.assertIn("OAN_HELM_FORK_CRED_ID", stage)
        for absent in ("KUBECONFIG", "helm upgrade", "kubectl", "docker ", "aws "):
            self.assertNotIn(absent, stage)
        self.assertIn("OAN_HELM_FORK_CRED_ID = 'oan-helm-fork-token'", self.text)
        self.assertIn("PIN_PR_CRED_ID = 'oan-ci-app'", self.text)

    def test_the_stage_uses_this_pipelines_ecr_names(self):
        self.assertIn("ECR_REPOSITORY = 'openg2p/farmer-registry'", self.text)
        for component in COMPONENTS:
            self.assertIn(component, self.text.split("stage('Publish')", 1)[1].split("stage('Deploy (package)')", 1)[0])
        self.assertIn("CHART = \"openg2p-farmer-registry\"", (ROOT / "ci/deploy/release_images.py").read_text())

    def test_braces_balance(self):
        self.assertEqual(self.text.count("{"), self.text.count("}"))


if __name__ == "__main__":
    unittest.main()
