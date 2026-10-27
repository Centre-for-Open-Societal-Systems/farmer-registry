"""Apply the tested ODK signing verification to new-dev without running setup jobs."""
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
PARTNER = ("Deployment", "farmer-registry-partner-api")
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import approved_chart


def command(args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=900)
    if result.returncode:
        raise RuntimeError("Partner deployment command failed; private output withheld")
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
    if set(old) != set(new) or PARTNER not in old:
        raise ValueError("Partner-only rollout must preserve every persistent resource")
    if any(d and d["kind"] == "Job" for d in after):
        raise ValueError("Partner-only rollout must not run setup jobs")
    previous = old[PARTNER]["spec"]["template"]["spec"]["containers"]
    current = new[PARTNER]["spec"]["template"]["spec"]["containers"]
    if len(previous) != 1 or len(current) != 1 or current[0]["image"] != image:
        raise ValueError("Expected exactly the pinned partner image")
    current[0]["image"] = previous[0]["image"]
    if old != new:
        raise ValueError("Partner-only rollout would change unrelated resources or configuration")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit) or not re.fullmatch(
        r"\d{12}\.dkr\.ecr\.ap-south-1\.amazonaws\.com/openg2p/farmer-registry/partner-api:"
        + re.escape(args.commit[:12]) + r"@sha256:[0-9a-f]{64}", args.image
    ):
        raise ValueError("Expected a commit-pinned Farmer partner digest")
    if args.apply:
        approved_chart.require_deployable("dev")
    helm = ["-n", NAMESPACE]
    status = json.loads(command(["helm", "status", RELEASE, *helm, "-o", "json"]))
    if status.get("info", {}).get("status") != "deployed":
        raise ValueError("Existing deployed Farmer release required")
    values = yaml.safe_load(command(["helm", "get", "values", RELEASE, *helm, "-o", "yaml"]))
    if values.get("global", {}).get("registryHostname") != "farmer-registry-development.oanstaging.com":
        raise ValueError("This rollout targets only the verified new-dev Farmer release")
    before = list(yaml.safe_load_all(command(["helm", "get", "manifest", RELEASE, *helm])))
    listed = json.loads(command(["helm", "list", *helm, "--filter", "^farmer-registry$", "-o", "json"]))
    if len(listed) != 1 or listed[0].get("name") != RELEASE:
        raise ValueError("Expected exactly the existing Farmer release")
    installed_chart = listed[0].get("chart")
    reference, digest = args.image.split("@", 1)
    repository, tag = reference.rsplit(":", 1)
    with tempfile.TemporaryDirectory(prefix="farmer-partner-rollout-") as work:
        work = Path(work)
        chart, chart_provenance = approved_chart.prepare(work, values, before, installed_chart)
        partner = values.setdefault("registry", {}).setdefault("partnerApi", {})
        partner.setdefault("image", {}).update(repository=repository, tag=tag + "@" + digest)
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
                raise ValueError("Partner rollout did not become ready")
        else:
            final = status
    result = {"environment": "dev", "component": "registry-partner-api", "commit": args.commit,
              "image": args.image, "helmRevision": final["version"], "previousHelmRevision": status["version"],
              "outcome": "deployed" if args.apply else "validated", "setupJobsExecuted": False, "chartProvenance": chart_provenance}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print("Partner-only rollout stopped: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print("Partner-only rollout stopped; private configuration withheld", file=sys.stderr)
        raise SystemExit(1)
