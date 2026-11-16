"""Which connector images ci/deploy/connector-staging.sh pins, with stand-in aws, helm and kubectl (no cluster, no
network). PLAN_ONLY=1 stops the script after it has written the image override, before oan-helm is fetched.
Same cases as livestock's test/test_connector_staging_build_tag.py."""
import io
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = "ci/deploy/connector-staging.sh"
PREFIX = "123456789012.dkr.ecr.ap-south-1.amazonaws.com/openg2p/farmer-registry"
COMMIT = "4db9d979983b" + "4" * 28
PROMOTED = "sha256:" + "d" * 64       # the staff-api digest the promoted chart pins
CONNECTOR = "sha256:" + "c" * 64
CONNECTOR_UI = "sha256:" + "e" * 64

HELM = "#!/usr/bin/env bash\nexit 0\n"
KUBECTL = "#!/usr/bin/env bash\nexit 0\n"
# describe-images by digest prints that digest's tags; by tag, the digest that tag is on now. Tags come from TAGS
# ("<repository-suffix>:<tag>=<digest>" lines), the promoted digest's tags from DIGEST_TAGS.
AWS = """#!/usr/bin/env bash
repo= ; ids=
while [ $# -gt 0 ]; do
  case "$1" in --repository-name) repo=$2; shift ;; --image-ids) ids=$2; shift ;; esac
  shift
done
case "$ids" in
  imageDigest=*) printf '%s\\n' "$DIGEST_TAGS" ;;
  imageTag=*) line=$(printf '%s\\n' "$TAGS" | grep -F "${repo##*/}:${ids#imageTag=}=" | head -n 1)
              test -n "$line" || exit 254
              echo "${line#*=}" ;;
esac
"""


def chart_archive(path, source_commit, staff_api=PREFIX + "/staff-api"):
    chart = "apiVersion: v2\nname: openg2p-farmer-registry\nversion: 1.0.0-rc.882\nannotations:\n"
    if source_commit:
        chart += f"  oan.org/source-commit: {source_commit}\n"
    values = f"registry:\n  staffApi:\n    image:\n      repository: {staff_api}\n      tag: 1.0.0-rc.882@{PROMOTED}\n"
    with tarfile.open(path, "w:gz") as bundle:
        for name, text in (("Chart.yaml", chart), ("values.yaml", values)):
            data = text.encode()
            info = tarfile.TarInfo(f"openg2p-farmer-registry/{name}")
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))


@unittest.skipUnless(shutil.which("bash") and shutil.which("python3"), "needs bash and python3")
class ConnectorBuildTagTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        (self.repo / "ci/deploy").mkdir(parents=True)
        shutil.copy(ROOT / SCRIPT, self.repo / SCRIPT)
        (self.repo / "built-chart").mkdir()
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        for name, body in (("helm", HELM), ("kubectl", KUBECTL), ("aws", AWS)):
            path = self.bin / name
            path.write_text(body, newline="\n")
            path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def run_script(self, source_commit, digest_tags, tags, **chart):
        chart_archive(self.repo / "built-chart/openg2p-farmer-registry-1.0.0-rc.882.tgz", source_commit, **chart)
        env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"], KUBECONFIG="/nonexistent",
                   PLAN_ONLY="1", DIGEST_TAGS=digest_tags, TAGS="\n".join(tags))
        done = subprocess.run(["bash", SCRIPT], cwd=str(self.repo), env=env, capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr

    def test_the_promoted_build_s_connector_images_are_pinned(self):
        code, out = self.run_script(COMMIT, "staging\t1.0.0-rc.882", [
            f"registry-connector:{COMMIT[:12]}={CONNECTOR}", f"registry-connector-ui:{COMMIT[:12]}={CONNECTOR_UI}"])
        self.assertEqual(code, 0, out)
        self.assertIn(f"Promoted chart is build {COMMIT[:12]} (chart commit {COMMIT[:12]};", out)
        self.assertIn(f"api, worker, beat, consumer: {PREFIX}/registry-connector@{CONNECTOR}", out)
        self.assertIn(f"ui: {PREFIX}/registry-connector-ui@{CONNECTOR_UI}", out)
        self.assertIn("PLAN_ONLY: nothing was changed.", out)

    def test_a_chart_without_the_commit_falls_back_to_the_digest_tag(self):
        code, out = self.run_script("", f"staging\t{COMMIT[:12]}", [
            f"registry-connector:{COMMIT[:12]}={CONNECTOR}", f"registry-connector-ui:{COMMIT[:12]}={CONNECTOR_UI}"])
        self.assertEqual(code, 0, out)
        self.assertIn(f"Promoted chart is build {COMMIT[:12]} (chart commit none recorded;", out)

    def test_no_build_tag_anywhere_fails_before_the_cluster(self):
        code, out = self.run_script("", "staging\t1.0.0-rc.882", [])
        self.assertNotEqual(code, 0)
        self.assertIn("Neither the promoted chart (oan.org/source-commit) nor staff-api", out)
        self.assertNotIn("PLAN_ONLY", out)

    def test_a_build_without_connector_images_fails(self):
        code, out = self.run_script(COMMIT, "staging", [f"registry-connector:{COMMIT[:12]}={CONNECTOR}"])
        self.assertNotEqual(code, 0)
        self.assertIn("No registry-connector and registry-connector-ui image carries a build tag", out)

    def test_no_promoted_chart_fails(self):
        env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"], KUBECONFIG="/nonexistent",
                   PLAN_ONLY="1")
        done = subprocess.run(["bash", SCRIPT], cwd=str(self.repo), env=env, capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("No promoted chart archive", done.stdout + done.stderr)


class OverrideShapeTest(unittest.TestCase):
    """The override matches oan-helm's addons/farmer-connector image keys (repository, tag "<tag>@<digest>")."""

    def test_the_script_writes_every_connector_workload(self):
        text = (ROOT / SCRIPT).read_text(encoding="utf-8")
        self.assertIn('for name in ("api", "worker", "beat", "consumer")', text)
        self.assertIn('override["ui"]', text)
        self.assertIn('"tag": f"{tag}@{digest}"', text)
        self.assertIn('deliver_staging_farmer_connector.sh" --values "$OVERRIDE"', text)


if __name__ == "__main__":
    unittest.main()
