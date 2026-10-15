#!/usr/bin/env python3
"""Audit private identity snapshots; print issuer metadata only, never tokens.

This checks configuration, not token signatures. AWE remains responsible for
signature/issuer/audience validation. No request mutates IAM or Keycloak.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.request import urlopen

import yaml

ISSUER = "https://keycloak-development.oanstaging.com/realms/staff"
IAM = "https://staff-iam-development.oanstaging.com"
OVERLAY = Path(__file__).resolve().parents[3] / "helm/environments/dev/registry-identity.yaml"
CHECKS = ("usersVerified", "clientsVerified", "rolesVerified", "audiencesVerified",
          "serviceAccountCredentialsVerified", "sharedPortalRoutingVerified",
          "issuerAndSignatureValidationVerified", "workerTokenSettingsVerified",
          "enabledHooksRehearsed", "hookRerunsVerified", "hookFailureRecoveryVerified")


def token_issuer(token):
    # Decode only to diagnose iss. Never return/log other token claims.
    part = token.strip().split(".")
    if len(part) != 3:
        raise ValueError("Malformed token")
    payload = json.loads(base64.urlsafe_b64decode(part[1] + "=" * (-len(part[1]) % 4)))
    return payload.get("iss")


def check(provider, awe_config, discovery, public_keys, internal_keys, review):
    if discovery.get("issuer") != ISSUER or provider.get("issuer") != ISSUER:
        raise ValueError("IAM/discovery issuer mismatch")
    if provider.get("id") != 1 or provider.get("active") is not True:
        raise ValueError("Expected active IAM provider 1")
    for field, suffix in (("authorization_endpoint", "/protocol/openid-connect/auth"),
                          ("token_endpoint", "/protocol/openid-connect/token"),
                          ("userinfo_endpoint", "/protocol/openid-connect/userinfo")):
        if provider.get(field) != ISSUER + suffix or discovery.get(field) != ISSUER + suffix:
            raise ValueError("IAM endpoint mismatch")
    if provider.get("server_metadata_url") != ISSUER + "/.well-known/openid-configuration":
        raise ValueError("IAM metadata URL mismatch")
    if provider.get("oauth_callback_url") != IAM + "/auth/callback":
        raise ValueError("IAM callback route mismatch")
    keycloak = awe_config.get("awe", {}).get("keycloak", {})
    if keycloak.get("issuer") != ISSUER or keycloak.get("realm") != "staff":
        raise ValueError("Effective AWE issuer/realm mismatch")
    if keycloak.get("base_url") != ISSUER.removesuffix("/realms/staff"):
        raise ValueError("Effective AWE base URL mismatch")
    if not keycloak.get("jwks_url"):
        raise ValueError("AWE JWKS validation must remain configured")
    if keycloak.get("audience", "") != review.get("aweAudience"):
        raise ValueError("AWE audience requirements have not been verified")
    def keys(document):
        # Compare public key material, not just kid (which can collide).
        fields = ("kty", "kid", "n", "e", "crv", "x", "y")
        return {tuple(k.get(f) for f in fields) for k in document.get("keys", [])}
    if not keys(public_keys) or keys(public_keys) != keys(internal_keys):
        raise ValueError("Internal and public JWKS must serve the same realm keys")
    if any(review.get(name) is not True for name in CHECKS):
        raise ValueError("Identity prerequisites or isolated hook rehearsals incomplete")
    if review.get("environment") != "dev" or review.get("issuer") != ISSUER:
        raise ValueError("Identity review belongs to another environment")
    # A review is supplied by the operator after inspecting users/clients/roles,
    # not inferred from a successful HTTP health check or an unsigned JWT.
    return {"environment": "dev", "issuer": ISSUER, "checkedAt": int(time.time()),
            "overlayHash": hashlib.sha256(OVERLAY.read_bytes()).hexdigest(),
            "checks": {name: True for name in CHECKS}}


def evidence(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    age = time.time() - value.get("checkedAt", 0)
    if not 0 <= age <= 3600 or value.get("environment") != "dev" or value.get("issuer") != ISSUER:
        raise ValueError("Identity evidence expired or environment mismatch")
    if value.get("overlayHash") != hashlib.sha256(OVERLAY.read_bytes()).hexdigest():
        raise ValueError("Identity values changed since readiness review")
    if any(value.get("checks", {}).get(name) is not True for name in CHECKS):
        raise ValueError("Identity readiness evidence incomplete")
    return value


def get_json(url):
    # Default HTTPS verification stays enabled. No insecure TLS option.
    with urlopen(url, timeout=20) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", type=Path, required=True, help="Private effective IAM provider JSON")
    parser.add_argument("--awe-config", type=Path, required=True, help="Private mounted effective AWE YAML")
    parser.add_argument("--review", type=Path, required=True, help="Operator review of realm prerequisites")
    parser.add_argument("--output", type=Path, required=True, help="Safe short-lived readiness evidence")
    parser.add_argument("--token-file", type=Path, help="Optional private token; inspect only iss")
    parser.add_argument("--internal-jwks-file", type=Path, required=True,
                        help="JWKS read from AWE's effective internal endpoint")
    args = parser.parse_args()
    discovery = get_json(ISSUER + "/.well-known/openid-configuration")
    if discovery.get("jwks_uri") != ISSUER + "/protocol/openid-connect/certs":
        raise ValueError("Unexpected public JWKS endpoint")
    result = check(json.loads(args.provider.read_text()), yaml.safe_load(args.awe_config.read_text()),
                   discovery, get_json(discovery["jwks_uri"]),
                   json.loads(args.internal_jwks_file.read_text()), json.loads(args.review.read_text()))
    if args.token_file and token_issuer(args.token_file.read_text()) != ISSUER:
        raise ValueError("Login token issuer mismatch; sign in again")
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PASS: effective IAM/AWE issuer " + ISSUER + "; realm prerequisites reviewed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("FAIL: identity readiness failed; private configuration and token withheld", file=sys.stderr)
        raise SystemExit(1)
