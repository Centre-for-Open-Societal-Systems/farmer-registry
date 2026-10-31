#!/usr/bin/env python3
"""Generate first-install evidence for the staging fresh-install action from live, read-only facts.

The rehearsal of a first install is New Dev: the images that run there now, built from one source
commit, are the images staging installs. Every field of the record is read from a cluster or from
this checkout, never typed in:

  * New Dev (namespace farmer): the deployed Helm release (revision, chart version, platform), the
    image reference of each component as the Deployment or Job spec pins it (tag and digest), and
    whether every Deployment is ready;
  * the pin (ci/deploy/oan-chart-staging.json): chart version and sha256, platform, values commit and
    sha256; the chart archive and the values file are downloaded and their sha256 is verified here;
  * staging: the deployed commons-services release (revision, chart version), the staging Gateway,
    and the absence of the target release and of every target database (read through psql in the
    Commons PostgreSQL pod; no password is printed or written);
  * this checkout: the delivery hash and the full source commit of the image tag.

Only get/exec-read operations are issued. Output holds no credentials. Upload the file to the Jenkins
file credential staging-farmer-rehearsal; the pipeline accepts it for 24 hours, only for the
fresh-install action, and only with the delivery hash of the staging branch it runs from.

Example (from a checkout of the branch Jenkins builds, with pyyaml available):

  uv run --no-project --with pyyaml python ci/deploy/staging_first_install_evidence.py \\
    --newdev-kubectl "ssh new-gen2-development sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml" \\
    --staging-kubectl "ssh openg2p-gen2-staging sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml" \\
    --output staging-farmer-rehearsal.json
"""
import argparse
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
sys.path.insert(0, str(ROOT / "ci" / "deploy"))
import oan_chart
import staging
from deployment import COMPONENTS
from environments import configuration

IMAGE = re.compile(r"(?P<repository>[^:@\s]+)(?::(?P<tag>[A-Za-z0-9_.-]+))?@(?P<digest>sha256:[0-9a-f]{64})")
NEW_DEV_NAMESPACE, RELEASE = "farmer", "farmer-registry"


def kubectl(prefix, *args):
    command = shlex.split(prefix)
    # ssh joins its arguments into one remote shell line: quote the kubectl arguments once for it.
    command += [shlex.join(args)] if command[0] == "ssh" else list(args)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("kubectl %s failed: %s" % (" ".join(args[:3]), result.stderr.strip()[:300]))
    return result.stdout


def get_json(prefix, *args):
    return json.loads(kubectl(prefix, "get", *args, "-o", "json"))


def helm_release(prefix, release, namespace):
    """Status, revision, chart version and appVersion of the newest Helm release secret."""
    secrets = get_json(prefix, "secrets", "-n", namespace, "-l", "owner=helm,name=" + release)["items"]
    if not secrets:
        return None
    newest = max(secrets, key=lambda s: int(s["metadata"]["labels"]["version"]))
    # Helm stores base64(gzip(json)) inside the Secret's own base64 data field.
    body = json.loads(gzip.decompress(base64.b64decode(base64.b64decode(newest["data"]["release"]))))
    return {"status": newest["metadata"]["labels"]["status"], "revision": int(newest["metadata"]["labels"]["version"]),
            "chartVersion": body["chart"]["metadata"]["version"], "platform": body["chart"]["metadata"].get("appVersion", "")}


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def pin_facts(offline):
    pin = oan_chart.profile("staging")
    if not offline:
        values_url, values_sha = oan_chart.values_url("staging")
        if hashlib.sha256(fetch(values_url)).hexdigest() != values_sha:
            raise RuntimeError("Environment values at the pinned commit do not match their sha256")
        chart_url = pin["repository"] + "%s-%s.tgz" % (pin["name"], pin["version"])
        if hashlib.sha256(fetch(chart_url)).hexdigest() != pin["sha256"]:
            raise RuntimeError("The pinned chart archive does not match its sha256")
    return {"chartVersion": pin["version"], "chartSha256": pin["sha256"], "platform": pin["platformVersion"],
            "valuesCommit": pin["values"]["commit"], "valuesSha256": pin["values"]["sha256"]}


def new_dev_facts(prefix, now):
    release = helm_release(prefix, RELEASE, NEW_DEV_NAMESPACE)
    if release is None or release["status"] != "deployed":
        raise RuntimeError("New Dev has no deployed farmer-registry release")
    deployments = {d["metadata"]["name"]: d for d in get_json(prefix, "deployments", "-n", NEW_DEV_NAMESPACE)["items"]}
    jobs = {j["metadata"]["name"]: j for j in get_json(prefix, "jobs", "-n", NEW_DEV_NAMESPACE)["items"]}
    images, ready = {}, True
    for kind, suffix, component in COMPONENTS.values():
        name = RELEASE + "-" + suffix
        obj = (deployments if kind == "Deployment" else jobs).get(name)
        if obj is None:
            raise RuntimeError("New Dev lacks %s %s" % (kind, name))
        refs = [IMAGE.fullmatch(c["image"]) for c in obj["spec"]["template"]["spec"]["containers"] if "/farmer-registry/" in c["image"]]
        if len(refs) != 1 or refs[0] is None or not refs[0]["tag"]:
            raise RuntimeError("%s must pin exactly one tag@digest image" % name)
        images[component] = refs[0].groupdict()
        if kind == "Deployment":
            status = obj.get("status", {})
            ready = ready and status.get("readyReplicas", 0) >= obj["spec"].get("replicas", 1) >= 1
    # celery worker and beat producer share one image; they must agree.
    for suffix, component in (("celery-beat-producer", "celery"),):
        beat = [IMAGE.fullmatch(c["image"]) for c in deployments[RELEASE + "-" + suffix]["spec"]["template"]["spec"]["containers"]
                if "/farmer-registry/" in c["image"]][0].groupdict()
        if beat != images[component]:
            raise RuntimeError("celery worker and beat producer run different images")
    tags = {i["tag"] for i in images.values()}
    if len(tags) != 1:
        raise RuntimeError("The New Dev components were not built from one source commit")
    tag = tags.pop()
    commit = subprocess.run(["git", "rev-parse", "--verify", tag + "^{commit}"], cwd=ROOT, capture_output=True, text=True)
    if commit.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", commit.stdout.strip()):
        raise RuntimeError("Image tag %s does not resolve to a commit in this checkout; fetch the full history" % tag)
    registries = {i["repository"].split("/")[0] for i in images.values()}
    if len(registries) != 1:
        raise RuntimeError("Components come from different registries")
    registry, source = registries.pop(), commit.stdout.strip()
    record_images = {}
    for component, ref in images.items():
        if ref["repository"] != registry + "/openg2p/farmer-registry/" + component:
            raise RuntimeError("Unexpected repository for " + component)
        # runtimeTested: this exact digest is the one running (ready) on New Dev now.
        record_images[component] = {"repository": ref["repository"], "tag": tag, "sourceCommit": source,
                                    "digest": ref["digest"], "runtimeTested": bool(ready)}
    return {"registry": {"registry": registry, "sourceCommit": source, "images": record_images},
            "newDev": {"release": RELEASE, "namespace": NEW_DEV_NAMESPACE, "status": release["status"],
                       "revision": release["revision"], "chartVersion": release["chartVersion"],
                       "platform": release["platform"], "allDeploymentsReady": bool(ready),
                       "observedAt": now}}


def staging_facts(prefix, now):
    configured = configuration("staging")
    commons = helm_release(prefix, "commons-services", "commons")
    if commons is None:
        raise RuntimeError("Staging has no commons-services release")
    gateway = get_json(prefix, "gateway", "staging", "-n", "istio-system")
    if "*.oanstaging.com" not in [h for server in gateway["spec"]["servers"] for h in server["hosts"]]:
        raise RuntimeError("The staging Gateway does not serve *.oanstaging.com")
    names = [configured["registryDatabase"], configured["idGeneratorDatabase"], configured["connectorDatabase"]]
    # Database names are fixed identifiers from the delivery contract, not user input.
    if not all(re.fullmatch(r"[a-z0-9_]+", name) for name in names):
        raise RuntimeError("Unexpected database name")
    listing = kubectl(prefix, "exec", "-n", "commons", "commons-postgresql-0", "--", "bash", "-c",
                      'PGPASSWORD="$POSTGRES_PASSWORD" psql -U postgres -tAc "select datname from pg_database"')
    existing = set(listing.split())
    namespaces = {n["metadata"]["name"] for n in get_json(prefix, "namespaces")["items"]}
    release = helm_release(prefix, RELEASE, configured["namespace"]) if configured["namespace"] in namespaces else None
    return {"stagingCommons": {"release": "commons-services", "namespace": "commons", "status": commons["status"],
                               "revision": commons["revision"], "chartVersion": commons["chartVersion"],
                               "gateway": "istio-system/staging", "observedAt": now},
            "target": {"namespace": configured["namespace"], "releasePresent": release is not None,
                       "databases": {name: ("present" if name in existing else "absent") for name in sorted(names)},
                       "observedAt": now}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--newdev-kubectl", required=True, help="command prefix that runs kubectl against New Dev (read only)")
    parser.add_argument("--staging-kubectl", required=True, help="command prefix that runs kubectl against staging (read only)")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offline", action="store_true", help="skip downloading the chart and values to verify their sha256")
    args = parser.parse_args()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dev, stg = new_dev_facts(args.newdev_kubectl, now), staging_facts(args.staging_kubectl, now)
    pin = pin_facts(args.offline)
    record = {"environment": "staging", "namespace": configuration("staging")["namespace"], "platform": pin["platform"],
              "mode": staging.FIRST_INSTALL, "deliveryHash": staging.delivery_hash(), "verifiedAt": now,
              "registry": dev["registry"],
              "firstInstall": {"rehearsalEnvironment": "new-dev", "pin": pin, "newDev": dev["newDev"],
                               "stagingCommons": stg["stagingCommons"], "target": stg["target"]}}
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    # The pipeline's own check, run here so a rejected record is never uploaded.
    try:
        staging.evidence(args.output, commit, allow_first_install=True)
    except Exception:
        args.output.unlink()
        raise
    print("Wrote %s (images tag %s, New Dev release revision %d, staging Commons revision %d)" % (
        args.output, next(iter(dev["registry"]["images"].values()))["tag"], dev["newDev"]["revision"], stg["stagingCommons"]["revision"]))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FAIL: " + str(error), file=sys.stderr)
        raise SystemExit(1)
