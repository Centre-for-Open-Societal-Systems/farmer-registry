"""Validate environment boundaries without printing credentials or private values."""
import argparse
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "dev": ("farmer", "farmer-dev-kubeconfig", "farmer-registry-development.oanstaging.com", "https://keycloak-development.oanstaging.com/realms/staff", "farmer-registry-connector"),
    "staging": ("far", "staging-farmer-kubeconfig", "farmer-registry.oanstaging.com", "https://keycloak.oanstaging.com/realms/staff", "farmer-registry-connector"),
}
RESOURCES = {
    "dev": {"registryDatabase": "farmer_registry", "connectorDatabase": "farmer_connector_v2",
            "connectorQueue": "farmer-registry-connector-v2",
            "connectorHostname": "connector-farmer-registry-development.oanstaging.com",
            "apiServers": ["https://13.201.58.55:6443"]},
    "staging": {"registryDatabase": "farmer_registry_far", "connectorDatabase": "farmer_connector_v2_far",
                "legacyConnectorDatabase": "farmer_connector_far",
                "connectorQueue": "farmer-registry-connector-v2-far",
                "connectorHostname": "connector-farmer-registry.far.staging.openg2p.test",
                "apiServers": ["https://10.0.1.212:6443", "https://52.66.116.220:6443"]},
}


def configuration(environment, root=ROOT):
    if environment not in EXPECTED:
        raise ValueError("Unknown delivery environment")
    data = yaml.safe_load((root / "helm/environments" / environment / "delivery.yaml").read_text(encoding="utf-8"))
    fields = ("namespace", "kubeconfigCredential", "registryHostname", "staffIssuer", "connectorRelease")
    if data.get("environment") != environment or tuple(data.get(k) for k in fields) != EXPECTED[environment]:
        raise ValueError("Delivery environment boundary changed; review its deployment contract")
    if any(data.get(k) != v for k, v in RESOURCES[environment].items()):
        raise ValueError("Delivery resource boundary changed; review the environment pair")
    return data


def namespace(environment):
    if environment not in EXPECTED:
        raise ValueError("Unknown delivery environment")
    return EXPECTED[environment][0]


def validate_cluster(environment, credential, context):
    expected = configuration(environment)
    if credential != expected["kubeconfigCredential"]:
        raise ValueError("Kubernetes credential belongs to another environment")
    clusters = context.get("clusters", [])
    if len(clusters) != 1 or clusters[0].get("cluster", {}).get("server") not in expected["apiServers"]:
        raise ValueError("Kubernetes server does not match the selected environment")


def connector_settings(environment, settings):
    expected = configuration(environment)
    for key, value in {"namespace": expected["namespace"], "database": expected["connectorDatabase"],
                       "queue": expected["connectorQueue"]}.items():
        if settings.get(key) != value:
            raise ValueError("Connector resource belongs to another environment")


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
