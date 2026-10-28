"""Read-only native parent/platform/package source contract; never selects an RC."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
ROLES = ("staff-api", "partner-api", "celery", "db-seed")


def check(root=ROOT):
    contract = json.loads((root / "ci/validation/native-release-contract.json").read_text(encoding="utf-8"))
    if set(contract["parents"]) != set(ROLES):
        raise ValueError("All four native Farmer parent roles must be reviewed")
    for role in ROLES:
        selected = contract["parents"][role]
        expected = {"dockerfile": f"docker/{role}/Dockerfile", "repository": f"openg2p/openg2p-farmer-registry-{role}"}
        if selected != expected:
            raise ValueError("Native Farmer parent path or repository changed")
        content = (root / selected["dockerfile"]).read_text(encoding="utf-8")
        versions = re.findall(r"^ARG FARMER_VERSION=(\S+)$", content, re.M)
        sources = re.findall(r"^FROM (\S+)$", content, re.M)
        if versions != [contract["farmerParentVersion"]] or sources != [selected["repository"] + ":${FARMER_VERSION}"]:
            raise ValueError("Native Farmer parent pin or FROM changed without contract review")
    pin = json.loads((root / "ci/deploy/oan-chart.json").read_text(encoding="utf-8"))
    if pin["platformVersion"] != contract["platformVersion"]:
        raise ValueError("Central platform pin differs from reviewed native release contract")
    if not re.fullmatch(r"https://raw\.githubusercontent\.com/Centre-for-Open-Societal-Systems/oan-helm/[0-9a-f]{40}/repository/", pin["repository"]) or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]):
        raise ValueError("Central archive must have immutable source and SHA256")
    return {"native_parent": contract["farmerParentVersion"], "platform": contract["platformVersion"],
            "numeric_version_equality_required": False, "central_chart": {key: pin[key] for key in ("name", "version", "repository", "sha256")},
            "native_worker_save_acceptance": contract["nativeWorkerSaveAcceptance"]}


if __name__ == "__main__":
    print(json.dumps(check(), sort_keys=True))
