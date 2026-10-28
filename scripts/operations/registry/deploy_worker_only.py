"""Apply the tested background-auth fix to dev without running setup jobs."""
import argparse
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import yaml

RELEASE = "farmer-registry"
NAMESPACE = "farmer"
WORKER = ("Deployment", "farmer-registry-celery-worker")
TOKEN_NAME = "REGISTRY_CELERY_WORKERS_AWE_TOKEN_URL"
TOKEN_URL = "https://keycloak-development.oanstaging.com/realms/staff/protocol/openid-connect/token"
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import approved_chart


def command(args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=900)
    if result.returncode:
        raise RuntimeError("Worker deployment command failed; private output withheld")
    return result.stdout


def guard(before, after, image):
    def index(documents):
        result = {}
        for item in documents:
            if not item or item["kind"] == "Job":
                continue
            key = item["kind"], item["metadata"]["name"]
            if item["metadata"].get("namespace", NAMESPACE) != NAMESPACE or key in result:
                raise ValueError("Resource namespace or identity changed")
            result[key] = copy.deepcopy(item)
        return result
    old, new = index(before), index(after)
    if set(old) != set(new) or WORKER not in old:
        raise ValueError("Worker-only rollout must preserve every persistent resource")
    if any(d and d["kind"] == "Job" for d in after):
        raise ValueError("Worker-only rollout must not run setup jobs")
    previous = old[WORKER]["spec"]["template"]["spec"]["containers"]
    current = new[WORKER]["spec"]["template"]["spec"]["containers"]
    if len(previous) != 1 or len(current) != 1 or current[0]["image"] != image:
        raise ValueError("Expected exactly the pinned worker image")
    current[0]["image"] = previous[0]["image"]
    def normalize_token_url(previous_container, current_container, required=False):
        old_env = {e["name"]: e for e in previous_container.get("env", [])}
        new_env = {e["name"]: e for e in current_container.get("env", [])}
        if TOKEN_NAME not in old_env and TOKEN_NAME not in new_env and not required:
            return
        if new_env.get(TOKEN_NAME) != {"name": TOKEN_NAME, "value": TOKEN_URL} or TOKEN_NAME not in old_env:
            raise ValueError("Expected the verified Commons staff token URL")
        current_container["env"] = [old_env[TOKEN_NAME] if e["name"] == TOKEN_NAME else e for e in current_container["env"]]
    normalize_token_url(previous[0], current[0], required=True)
    # The pinned postgres-checker init container inherits the same envVars.
    old_init = old[WORKER]["spec"]["template"]["spec"].get("initContainers", [])
    new_init = new[WORKER]["spec"]["template"]["spec"].get("initContainers", [])
    if len(old_init) != len(new_init):
        raise ValueError("Worker init containers changed")
    for previous_container, current_container in zip(old_init, new_init):
        normalize_token_url(previous_container, current_container)
    if old != new:
        raise ValueError("Worker-only rollout would change unrelated resources or configuration")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit) or not re.fullmatch(
        r"\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com/openg2p/farmer-registry/celery:"
        + re.escape(args.commit[:12]) + r"@sha256:[0-9a-f]{64}", args.image
    ):
        raise ValueError("Expected a commit-pinned Farmer worker digest")
    if args.apply:
        approved_chart.require_deployable("dev")
    helm = ["-n", NAMESPACE]
    status = json.loads(command(["helm", "status", RELEASE, *helm, "-o", "json"]))
    if status.get("info", {}).get("status") != "deployed":
        raise ValueError("Existing deployed Farmer release required")
    values = yaml.safe_load(command(["helm", "get", "values", RELEASE, *helm, "-o", "yaml"]))
    if values.get("global", {}).get("registryHostname") != "farmer-registry-development.oanstaging.com":
        raise ValueError("This rollout targets only the verified dev Farmer release")
    before = list(yaml.safe_load_all(command(["helm", "get", "manifest", RELEASE, *helm])))
    listed = json.loads(command(["helm", "list", *helm, "--filter", "^farmer-registry$", "-o", "json"]))
    if len(listed) != 1 or listed[0].get("name") != RELEASE:
        raise ValueError("Expected exactly the existing Farmer release")
    installed_chart = listed[0].get("chart")
    reference, digest = args.image.split("@", 1)
    repository, tag = reference.rsplit(":", 1)
    with tempfile.TemporaryDirectory(prefix="farmer-worker-rollout-") as work:
        work = Path(work)
        chart, chart_provenance = approved_chart.prepare(work, values, before, installed_chart)
        worker = values.setdefault("registry", {}).setdefault("celeryWorker", {})
        worker.setdefault("image", {}).update(repository=repository, tag=tag + "@" + digest)
        worker.setdefault("envVars", {})[TOKEN_NAME] = TOKEN_URL
        worker.setdefault("envVarsFrom", {}).pop(TOKEN_NAME, None)
        private_values = work / "values.yaml"
        private_values.write_text(yaml.safe_dump(values)); private_values.chmod(0o600)
        renderer = approved_chart.renderer(work, chart, private_values)
        render_args = ["-f", str(private_values), "--no-hooks", "--post-renderer", str(renderer)]
        after = list(yaml.safe_load_all(command(["helm", "template", RELEASE, str(chart), *helm,
                                               *render_args, "--is-upgrade", "--dry-run=server"])))
        guard(before, after, args.image)
        current = json.loads(command(["helm", "status", RELEASE, *helm, "-o", "json"]))
        if (current.get("version"), current.get("info", {}).get("status")) != (status["version"], "deployed"):
            raise ValueError("Farmer release changed during preflight")
        if args.apply:
            command(["helm", "upgrade", RELEASE, str(chart), *helm, *render_args,
                     "--atomic", "--wait", "--timeout", "10m"])
            final = json.loads(command(["helm", "status", RELEASE, *helm, "-o", "json"]))
            guard(before, list(yaml.safe_load_all(command(["helm", "get", "manifest", RELEASE, *helm]))), args.image)
            if final.get("info", {}).get("status") != "deployed":
                raise ValueError("Worker rollout did not become ready")
        else:
            final = status
    result = {"environment": "dev", "component": "registry-worker", "commit": args.commit,
              "image": args.image, "helmRevision": final["version"], "previousHelmRevision": status["version"],
              "outcome": "deployed" if args.apply else "validated", "setupJobsExecuted": False, "chartProvenance": chart_provenance}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print("Worker-only rollout stopped: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print("Worker-only rollout stopped; private configuration withheld", file=sys.stderr)
        raise SystemExit(1)
