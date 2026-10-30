"""Separate immutable image publication from dev deployment.

DELIVERY_ACTION selects what a build does. publish-only builds and pushes the
images. deploy upgrades the existing dev release with them. fresh-install
rebuilds dev from an empty database with the same images and chart
(ci/deploy/fresh-install-dev.sh). connector-plan and connector-upgrade build
no images and only touch the farmer-registry-connector release
(ci/connector/upgrade-farmer-connector.sh).
"""
import json
import os
from pathlib import Path
import sys

ACTIONS = ("publish-only", "deploy", "fresh-install", "connector-plan", "connector-upgrade")


def action(environment):
    selected = environment.get("DELIVERY_ACTION") or "publish-only"
    if selected not in ACTIONS:
        raise ValueError("Unknown delivery action")
    return selected


def publication(environment):
    # Reuse the deployment guard: all six components, exact source/tag/ECR
    # repository, unique entries and SHA-256 digests are mandatory.
    sys.path.insert(0, str(Path(__file__).resolve().parent / "deploy"))
    from deployment import registry_provenance
    selected = action(environment)
    images = registry_provenance(environment["ECR_REGISTRY"],
                                 environment["IMAGE_TAG"], environment["SOURCE_COMMIT"])
    return {"component": "farmer-registry", "sourceCommit": environment["SOURCE_COMMIT"],
            "deliveryAction": selected, "images": images,
            "verification": "immutable-images-published",
            "deployment": "not-attempted-by-publication",
            "acceptance": "pending-live-application-checks"}


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["action"]:
            print(action(os.environ))
        elif len(sys.argv) == 3 and sys.argv[1] == "publication":
            Path(sys.argv[2]).write_text(json.dumps(publication(os.environ), indent=2) + "\n", encoding="utf-8")
        else:
            raise ValueError("Unknown delivery command")
    except (ValueError, KeyError, OSError):
        sys.exit("FAIL: invalid Farmer delivery action or image provenance")
