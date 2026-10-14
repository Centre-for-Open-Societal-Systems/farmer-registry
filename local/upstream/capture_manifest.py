"""Record the local trial's source commits and resolved image identities."""
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def output(*args):
    return subprocess.check_output(args, text=True, cwd=ROOT).strip()


def main():
    source = json.loads((HERE / "compose.template.json").read_text())
    refs = {s["image"] for s in source["services"].values() if "${" not in s["image"]}
    refs.add("openg2p/openg2p-id-generator:1.0.0")
    refs.update("openg2p/openg2p-registry-" + name + ":1.2.2-rc.544"
                for name in ("staff-api", "partner-api", "celery", "db-seed", "sanity-tests"))
    images = []
    for ref in sorted(refs):
        result = subprocess.run(["docker", "image", "inspect", ref], capture_output=True, text=True)
        if result.returncode:
            images.append({"reference": ref, "available_locally": False})
            continue
        data = json.loads(result.stdout)[0]
        images.append({"reference": ref, "id": data["Id"], "repo_digests": data.get("RepoDigests", [])})
    manifest = {
        "upstream_repository": "https://github.com/OpenG2P/farmer-registry.git",
        "upstream_layout_commit": output("git", "rev-parse", "HEAD"),
        "coss_source_commit": output("git", "-C", str(ROOT.parent / "farmer-gen2-common"), "rev-parse", "HEAD"),
        "registry_platform": "1.2.2-rc.544",
        "commons_base_contract": "2.3.3",
        "commons_services_contract": "2.3.4-rc.245",
        "note": "Local trial with uncommitted COSS overlay; source layout commit is not an RC release tag. Image identities describe this run, not a deployment lock.",
        "images": images,
    }
    (HERE / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
