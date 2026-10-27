"""Separate immutable image publication from guarded New Dev deployment."""
import json
import os
from pathlib import Path
import sys


def action(environment):
    selected = environment.get("NEW_DEV_DELIVERY_ACTION") or "publish-only"
    reset = environment.get("NEW_DEV_RESET_ACTION") or "check"
    if selected not in ("publish-only", "deploy"):
        raise ValueError("Unknown New Dev delivery action")
    if reset not in ("check", "initialize", "resume"):
        raise ValueError("Unknown New Dev reset action")
    if selected != "deploy" and reset != "check":
        raise ValueError("Publication cannot request a database reset")
    return selected


def publication(environment):
    # Reuse the deployment guard: all six components, exact source/tag/ECR
    # repository, unique entries and SHA-256 digests are mandatory.
    sys.path.insert(0, str(Path(__file__).resolve().parent / "deploy"))
    from deployment import registry_provenance
    selected = action(environment)
    if environment.get("OAN_DELIVERY_ACTION") != selected:
        raise ValueError("Delivery action changed after validation")
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
