#!/usr/bin/env python3
"""Offline gate for the rendered Gen2 dev release. Never prints secret values.

Usage: python scripts/operations/commons/validate_manifest.py rendered.yaml
Requires PyYAML (scripts/operations/commons/requirements.txt). Importable by the Helm regression tests.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlsplit

import yaml


def documents(text):
    return [doc for doc in yaml.safe_load_all(text) if isinstance(doc, dict)]


def pod_spec(doc):
    spec = doc.get("spec", {})
    if doc.get("kind") == "CronJob":
        spec = spec.get("jobTemplate", {}).get("spec", {})
    return spec.get("template", {}).get("spec", {})


def environments(doc):
    spec = pod_spec(doc)
    for container in spec.get("initContainers", []) + spec.get("containers", []):
        yield container, {env["name"]: env.get("value") for env in container.get("env", [])}


def validate(docs, release="farmer-registry", namespace="farmer", allow_examples=False):
    errors = []
    if namespace == "commons":
        errors.append("the registry namespace must be separate from shared commons")
    by_name = {(d.get("kind"), d.get("metadata", {}).get("name")): d for d in docs}
    alias = by_name.get(("Service", "commons-services-awe"), {})
    if alias:
        errors.append("the farmer chart must reuse, not recreate or adopt, the platform-owned AWE alias")

    def deployment_env(suffix):
        doc = by_name.get(("Deployment", f"{release}-{suffix}"), {})
        if not doc:
            errors.append(f"missing {suffix} Deployment")
        envs = list(environments(doc))
        return envs[-1][1] if envs else {}

    staff = deployment_env("staff-portal-api")
    partner = deployment_env("partner-api")
    worker = deployment_env("celery-worker")
    ui = deployment_env("staff-portal-ui")
    expected = {
        "REGISTRY_STAFF_PORTAL_API_DB_HOSTNAME": "commons-postgresql.commons.svc.cluster.local",
        "REGISTRY_STAFF_PORTAL_API_AUTH_PROVIDER_API_URL": "http://commons-services-iam-staff-portal-api.commons.svc.cluster.local",
        "REGISTRY_STAFF_PORTAL_API_AUTH_REDIS_URL": "redis://commons-redis-master.commons.svc.cluster.local:6379/0",
        "REGISTRY_STAFF_PORTAL_API_AWE_BASE_URL": "http://commons-services-awe.commons.svc.cluster.local",
        "REGISTRY_STAFF_PORTAL_API_MASTER_DATA_API_URL": "http://commons-services-master-data-api.commons.svc.cluster.local",
        "REGISTRY_STAFF_PORTAL_API_CSRF_ENABLED": "true",
        "REGISTRY_STAFF_PORTAL_API_KEYCLOAK_CLIENT_ID": f"{release}-staff-portal",
        "REGISTRY_STAFF_PORTAL_API_AUDIT_ENABLED": "true",
        "REGISTRY_STAFF_PORTAL_API_AUDIT_MANAGER_URL": "http://commons-services-auditmanager.commons.svc.cluster.local:80",
        "NOTIFICATION_ENABLED": "false",
    }
    for name, value in expected.items():
        if staff.get(name) != value:
            errors.append(f"{name} does not match the Gen2 common contract")
    for name, value in {
        "REGISTRY_PARTNER_API_SIGNATURE_VALIDATION_ENABLED": "true",
        "REGISTRY_PARTNER_API_CONSENT_ENFORCEMENT_ENABLED": "true",
        "REGISTRY_PARTNER_API_CRYPTO_BACKEND": "partner-mgmt",
        "REGISTRY_PARTNER_API_PARTNER_MGMT_API_URL": "http://commons-services-pm-partner-api.commons.svc.cluster.local",
        "REGISTRY_PARTNER_API_CONSENT_MANAGER_URL": "http://commons-services-cm-partner-api.commons.svc.cluster.local",
        "REGISTRY_PARTNER_API_AUDIT_MANAGER_URL": "http://commons-services-auditmanager.commons.svc.cluster.local:80",
    }.items():
        if partner.get(name) != value:
            errors.append(f"{name} does not match the Gen2 common security contract")
    for name, value in {
        "REGISTRY_CELERY_WORKERS_AWE_BASE_URL": "http://commons-services-awe.commons.svc.cluster.local",
        "REGISTRY_CELERY_WORKERS_AWE_ENABLED": "true",
        "REGISTRY_CELERY_WORKERS_AWE_DEFAULT_CALLBACK_URL": f"http://{release}-staff-portal-api.{namespace}.svc.cluster.local/awe/webhooks/decision",
        "REGISTRY_CELERY_WORKERS_AWE_CLIENT_ID": f"{release}-staff-portal",
        "NOTIFICATION_ENABLED": "false",
    }.items():
        if worker.get(name) != value:
            errors.append(f"{name} does not match the Gen2 common contract")
    if ui.get("MASTERDATA_BACKEND_API_URL") != expected["REGISTRY_STAFF_PORTAL_API_MASTER_DATA_API_URL"]:
        errors.append("staff UI must use the shared Master Data API")
    if ui.get("APPLICATION_MNEMONIC") != f"{release}-staff-portal":
        errors.append("staff UI application mnemonic must match the registry Keycloak client")

    def public_host(value, label):
        host = urlsplit(str(value or "")).hostname or ""
        if urlsplit(str(value or "")).scheme != "https" or not host or "." not in host:
            errors.append(f"{label} must be a browser-reachable HTTPS URL")
        if host.endswith(".svc.cluster.local") or host == "localhost":
            errors.append(f"{label} must not expose a cluster-only address")
        if not allow_examples and (host.endswith(".example.org") or host in {
            f"{release}.{namespace}.openg2p.org", f"staff-iam.{namespace}.openg2p.org",
            f"keycloak.{namespace}.openg2p.org", f"minio-api.{namespace}.openg2p.org",
        }):
            errors.append(f"{label} still uses an example/default hostname; supply real browser values")
        return host

    minio_host = str(staff.get("REGISTRY_STAFF_PORTAL_API_MINIO_ENDPOINT") or "")
    public_host("https://" + minio_host, "MINIO_ENDPOINT")
    if staff.get("REGISTRY_STAFF_PORTAL_API_MINIO_SECURE") != "true":
        errors.append("browser-facing MinIO must use HTTPS")
    browser_envs = [("staff UI", ui)]
    public_ui = by_name.get(("Deployment", f"{release}-staff-portal-ui-public"))
    if public_ui:
        browser_envs.append(("public staff UI", list(environments(public_ui))[-1][1]))
    for label, browser in browser_envs:
        portal_host = public_host(browser.get("APP_URL"), f"{label} APP_URL")
        iam_host = public_host(browser.get("IAM_URL"), f"{label} IAM_URL")
        logout_host = public_host(browser.get("KEYCLOAK_LOGOUT_URL"), f"{label} KEYCLOAK_LOGOUT_URL")
        cookie = str(browser.get("COOKIE_DOMAIN") or "").lstrip(".")
        if not cookie or not all(host == cookie or host.endswith("." + cookie) for host in (portal_host, iam_host)):
            errors.append(f"{label} COOKIE_DOMAIN must cover both the IAM and farmer portal browser hosts")
        issuer = str(worker.get("REGISTRY_CELERY_WORKERS_AWE_TOKEN_ISSUER_BASE_URL") or "")
        if urlsplit(issuer).hostname != logout_host or urlsplit(issuer).scheme != "https":
            errors.append(f"{label}: worker token issuer must match the public HTTPS Keycloak origin")
        if "https://" + minio_host not in str(browser.get("CSP_SRC_IMG") or "").split():
            errors.append(f"{label} CSP must allow the same MinIO host the API signs against")
        if browser.get("LOGIN_PROVIDER_ID") != "1":
            errors.append(f"{label} LOGIN_PROVIDER_ID must be 1 for the IAM client")
        if browser.get("MASTERDATA_BACKEND_API_URL") != expected["REGISTRY_STAFF_PORTAL_API_MASTER_DATA_API_URL"]:
            errors.append(f"{label} must use shared Master Data")
        if browser.get("APPLICATION_MNEMONIC") != f"{release}-staff-portal":
            errors.append(f"{label} application mnemonic must match the registry Keycloak client")

    seed = by_name.get(("Job", f"{release}-db-seed"), {})
    for _, env in environments(seed):
        if "LOAD_SAMPLE_DATA" in env:
            for name in ("LOAD_GEO_DATA", "LOAD_SAMPLE_DATA", "LOAD_IMAGES"):
                if env.get(name) != "false":
                    errors.append(f"{name} must be disabled on an existing Gen2 database")
            if env.get("AWE_CALLBACK_CALLER_SERVICE") != f"http://{release}-staff-portal-api.{namespace}.svc.cluster.local/awe/webhooks/decision":
                errors.append("db-seed must register the namespace-qualified AWE callback")
    if not seed:
        errors.append("registry metadata/db-seed Job must be enabled")
    if ("Job", f"{release}-fr-bulk-sample") in by_name:
        errors.append("bulk sample generation must be disabled")
    # These are external credentials, not the registry/client secrets created by
    # init Jobs. Guard every reference (including analytics), not just API envs.
    for doc in docs:
        for _, env in environments(doc):
            for name, value in env.items():
                if (name.endswith("DB_HOSTNAME") or name in ("PGHOST", "MD_PGHOST", "MDS_PGHOST", "AWE_PGHOST")) and value:
                    if value != "commons-postgresql.commons.svc.cluster.local":
                        errors.append(f"{doc['metadata']['name']}: {name} points at the wrong PostgreSQL")
        for container, _ in environments(doc):
            for entry in container.get("env", []):
                if entry["name"] in ("MD_PGPASSWORD", "MDS_PGPASSWORD"):
                    ref = entry.get("valueFrom", {}).get("secretKeyRef", {})
                    if ref != {"name": "master-data-db-user", "key": "master-data-db-user-password"}:
                        errors.append(f"{doc['metadata']['name']}: Master Data secret reference does not match the RC")
        if doc.get("kind") in ("Deployment", "StatefulSet"):
            if doc["metadata"]["name"].startswith(("commons-", "commons-services-")):
                errors.append("the farmer release must not deploy shared platform workloads")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--release", default="farmer-registry")
    parser.add_argument("--namespace", default="farmer")
    args = parser.parse_args()
    errors = validate(documents(args.manifest.read_text(encoding="utf-8")), args.release, args.namespace)
    if errors:
        for error in errors:
            print("FAIL:", error)
        return 1
    print("Gen2 rendered manifest: farmer/commons wiring, browser URLs, callbacks and seed safety OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
