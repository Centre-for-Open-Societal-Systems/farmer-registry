"""Image publication and dev delivery.

Every develop build publishes the immutable images and then DELIVERY_ACTION
decides what happens to the dev release. deploy (the default, no button needed)
upgrades the existing release with those images and the pinned chart, and Helm
puts the previous revision back when the upgrade fails (ci/deploy/deploy-rc.sh).
fresh-install rebuilds dev from an empty database with the same images and chart
(ci/deploy/fresh-install-dev.sh); it stays a deliberate choice.

A branch-index or first build may carry a stale parameter definition: an empty
value or the retired publish-only choice means the default, deploy.
"""
import json
import os
from pathlib import Path
import sys

ACTIONS = ("deploy", "fresh-install")
RETIRED = ("publish-only",)


def action(environment):
    selected = environment.get("DELIVERY_ACTION") or "deploy"
    if selected in RETIRED:
        selected = "deploy"
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
