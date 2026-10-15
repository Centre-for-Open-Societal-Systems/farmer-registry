"""Validate environment boundaries without printing credentials or private values."""
import argparse
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "dev": ("farmer", "farmer-dev-kubeconfig", "farmer-registry-development.oanstaging.com", "https://keycloak-development.oanstaging.com/realms/staff", "farmer-registry-connector"),
    "staging": ("far", "staging-farmer-kubeconfig", "farmer-registry.oanstaging.com", "https://keycloak.oanstaging.com/realms/staff", "farmer-connector"),
}


def configuration(environment, root=ROOT):
    if environment not in EXPECTED:
        raise ValueError("Unknown delivery environment")
    data = yaml.safe_load((root / "helm/environments" / environment / "delivery.yaml").read_text(encoding="utf-8"))
    fields = ("namespace", "kubeconfigCredential", "registryHostname", "staffIssuer", "connectorRelease")
    if data.get("environment") != environment or tuple(data.get(k) for k in fields) != EXPECTED[environment]:
        raise ValueError("Delivery environment boundary changed; review its deployment contract")
    return data


def validate_release(environment, status, values):
    expected = configuration(environment)
    if (status.get("name"), status.get("namespace"), status.get("info", {}).get("status")) != ("farmer-registry", expected["namespace"], "deployed"):
        raise ValueError("Existing deployed release in the selected environment required")
    if values.get("global", {}).get("registryHostname") != expected["registryHostname"]:
        raise ValueError("Release hostname does not match the selected environment")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", choices=EXPECTED)
    parser.add_argument("--status", type=Path)
    parser.add_argument("--values", type=Path)
    args = parser.parse_args()
    configuration(args.environment)
    if bool(args.status) != bool(args.values):
        parser.error("Provide both status and values")
    if args.status:
        validate_release(args.environment, json.loads(args.status.read_text()), yaml.safe_load(args.values.read_text()))
    print(json.dumps({"environment": args.environment, "configurationVerified": True}))


if __name__ == "__main__":
    main()
