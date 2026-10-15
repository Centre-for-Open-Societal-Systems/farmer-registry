#!/usr/bin/env python3
"""Validate a rendered new-dev Commons release or live YAML; never apply it.

Usage: python scripts/operations/commons/check_pm_manifest.py rendered-commons.yaml
Requires PyYAML (scripts/operations/commons/requirements.txt). Secret documents are never printed.
"""
import json
import sys
from pathlib import Path

import yaml

ISSUER = "https://keycloak-development.oanstaging.com/realms/staff"
JWKS = "http://commons-keycloak:80/realms/staff/protocol/openid-connect/certs"
PM_HOST = "partner-management-staff-portal-api.commons-dev.oanstaging.com"
IAM_HOST = "staff-iam-development.oanstaging.com"


def validate(documents):
    resources = []
    for doc in documents:
        if doc:
            resources.extend(doc.get("items", []) if doc.get("kind") == "List" else [doc])

    def resource(kind, name):
        matches = [r for r in resources if r.get("kind") == kind
                   and r.get("metadata", {}).get("name") == name]
        if len(matches) != 1:
            raise ValueError(f"Expected one {kind}/{name}")
        return matches[0]

    def env(name):
        deployment = resource("Deployment", name)
        containers = deployment["spec"]["template"]["spec"]["containers"]
        if len(containers) != 1:
            raise ValueError(f"Review containers in {name}")
        values = containers[0].get("env", [])
        if len({e['name'] for e in values}) != len(values):
            raise ValueError(f"Duplicate environment entries in {name}")
        return {e["name"]: e.get("value") for e in values}

    pm = env("commons-services-pm-staff-portal-api")
    for prefix in ("PARTNER_MANAGER_AUTH_", "COMMON_AUTH_"):
        issuers = json.loads(pm.get(prefix + "DEFAULT_ISSUERS", "[]"))
        keys = json.loads(pm.get(prefix + "DEFAULT_JWKS_URLS", "[]"))
        if len(issuers) != len(keys) or ISSUER not in issuers or keys[issuers.index(ISSUER)] != JWKS:
            raise ValueError(f"Incorrect issuer/JWKS mapping: {prefix}")
        if "http://commons-keycloak:80/realms/staff" in issuers:
            raise ValueError("Internal Keycloak URL must not be a trusted issuer")
    for field, expected in {
        "PARTNER_MANAGER_AUTH_ENABLED": "true",
        "PARTNER_MANAGER_AUTH_ADMIN_ROLE": "partner_manager",
        "PARTNER_MANAGER_AUTH_ADMIN_CLIENT_ID": "commons-services-staff-portal",
    }.items():
        if pm.get(field) != expected:
            raise ValueError(f"Unexpected {field}")
    if pm["PARTNER_MANAGER_AUTH_DEFAULT_ISSUERS"] != pm["COMMON_AUTH_DEFAULT_ISSUERS"]:
        raise ValueError("Issuer prefixes disagree")
    if pm["PARTNER_MANAGER_AUTH_DEFAULT_JWKS_URLS"] != pm["COMMON_AUTH_DEFAULT_JWKS_URLS"]:
        raise ValueError("JWKS prefixes disagree")
    for name, host in (("commons-services-pm-staff-portal-api", PM_HOST),
                       ("commons-services-iam-staff-portal-api", IAM_HOST)):
        route = resource("VirtualService", name)
        if route["spec"].get("hosts") != [host]:
            raise ValueError(f"Incorrect hostname for {name}")
        targets = [r.get("destination", {}).get("host") for h in route["spec"].get("http", [])
                   for r in h.get("route", [])]
        if targets != [name]:
            raise ValueError(f"Incorrect destination for {name}")
        for other in resources:
            if other.get("kind") == "VirtualService" and other is not route:
                if host in other.get("spec", {}).get("hosts", []):
                    raise ValueError(f"Duplicate VirtualService host: {host}")
    ui = env("commons-services-pm-staff-portal-ui")
    if ui.get("KEYCLOAK_LOGOUT_URL") != ISSUER + "/protocol/openid-connect/logout":
        raise ValueError("PM logout must use public Keycloak URL")
    for field, expected in {
        "STAFF_PORTAL_API_URL": "http://commons-services-pm-staff-portal-api",
        "IAM_URL": "http://commons-services-iam-staff-portal-api",
        "REDIRECT_URL": "https://partner-management-development.oanstaging.com",
    }.items():
        if ui.get(field) != expected:
            raise ValueError(f"Unexpected PM UI {field}")


if __name__ == "__main__":
    try:
        validate(yaml.safe_load_all(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except (ValueError, KeyError, IndexError, OSError, yaml.YAMLError) as error:
        print(f"FAIL: PM manifest validation ({type(error).__name__}): {error}", file=sys.stderr)
        raise SystemExit(1)
    print("PASS: PM issuer/JWKS, role enforcement, separate IAM/PM routes and browser URLs")
