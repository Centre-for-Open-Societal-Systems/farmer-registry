#!/usr/bin/env python3
"""Render two independent local Compose projects. No Docker or network calls.

Requires PyYAML (also used by ci/gen2). Generated paths are absolute so a
worktree builds its own code, never the unrelated sibling develop checkout.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
KC = "http://keycloak.localtest.me:8080"
ISSUER = KC + "/realms/farmer"
IAM = "http://iam.farmer.localtest.me:8100"
PORTAL = "http://portal.farmer.localtest.me:3100"
HUB = "http://staff.farmer.localtest.me:3102"
MINIO = "minio.farmer.localtest.me:9100"
PASSWORD = "${POSTGRES_PASSWORD:-postgres}"
SHARED = (
    "postgres", "redis", "minio", "minio-init", "keycloak", "keycloak-init",
    "iam-staff-api", "awe", "awe-ui", "farmer-master-data-api",
)
FARMER = (
    "id-generator", "farmer-registry-staff-api", "farmer-registry-partner-api",
    "farmer-registry-celery-worker", "farmer-registry-celery-beat",
    "farmer-registry-staff-ui", "farmer-registry-db-seed",
)
PINS = {
    "iam-staff-api": "openg2p/iam-staff-portal-api:1.4.4-rc.125",
    "farmer-master-data-api": "openg2p/master-data-api:1.1.4-rc.104",
    "awe": "openg2p/openg2p-awe:1.2.2",
    "awe-ui": "openg2p/openg2p-awe-ui:1.2.2",
}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8", newline="\n")


def asset(out, name, source, replacements):
    text = (ROOT / source).read_text(encoding="utf-8")
    for old, new in replacements:
        text = text.replace(old, new)
    write(out / name, text)
    return (out / name).as_posix()


def prepare(service, name, project, owned):
    service = copy.deepcopy(service)
    service["container_name"] = (
        "openg2p-shared-" + name if project == "shared" else "farmer-registry-" + name.removeprefix("farmer-registry-")
    )
    service["depends_on"] = {k: v for k, v in service.get("depends_on", {}).items() if k in owned}
    # No placeholders or cross-project depends_on: startup explicitly probes
    # the shared services. Both projects join an existing, dedicated network.
    service["networks"] = ["default"]
    service["extra_hosts"] = [f"{host}:host-gateway" for host in (
        "keycloak.localtest.me", "iam.farmer.localtest.me", "minio.farmer.localtest.me",
    )]
    if "build" in service:
        service["build"]["context"] = ROOT.as_posix()
        # Do not overwrite the images used by the old stack during rehearsal.
        service["image"] = service["image"].replace("farmer-registry-local/", "farmer-gen2-local/")
    elif name in ("farmer-registry-celery-beat",):
        service["image"] = "farmer-gen2-local/celery:dev"
    for i, mount in enumerate(service.get("volumes", [])):
        if mount.startswith("./"):
            source, target = mount.split(":", 1)
            service["volumes"][i] = (ROOT / source).as_posix() + ":" + target
    env = service.get("environment", {})
    for key, value in list(env.items()):
        value = str(value)
        value = value.replace("redis://redis:6379/0", "redis://redis:6379/4")
        value = value.replace("http://localhost:${KEYCLOAK_PORT:-8080}", KC)
        value = value.replace("/realms/staff", "/realms/farmer")
        if value in ("iam_staff", "awe", "idgenerator"):
            value = {"iam_staff": "farmer_iam", "awe": "farmer_awe", "idgenerator": "farmer_idgenerator"}[value]
        if key.endswith("MINIO_ENDPOINT"):
            value = MINIO
        if "COOKIE_DOMAIN" in key:
            value = "farmer.localtest.me"
        env[key] = value
    if name in PINS:
        service["image"] = PINS[name]
    return service


def render(out):
    out = Path(out).resolve()
    source = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    shared = {n: prepare(source[n], n, "shared", SHARED) for n in SHARED}
    farmer = {n: prepare(source[n], n, "farmer", FARMER) for n in FARMER}
    replacements = [("http://localhost:8080", KC), ("http://keycloak:8080", KC),
                    ("/realms/staff", "/realms/farmer"), ('realm: "staff"', 'realm: "farmer"'),
                    ("http://localhost:8020", IAM), ("http://localhost:3001", HUB)]
    for name, filename, target in (
        ("iam-staff-api", "iam-login-providers.json", "/opt/iam-staff-portal-data/login_providers.json"),
        ("awe", "awe-config.yaml", "/app/config/default.yaml"),
        ("awe-ui", "awe-ui-config.json", "/usr/share/nginx/html/config.json"),
    ):
        path = asset(out, filename, "docker/local-dev/" + filename, replacements)
        if filename.endswith(".json"):
            data = json.loads(Path(path).read_text())
            if name == "awe-ui":
                data["keycloak"]["realm"] = "farmer"
            write(Path(path), json.dumps(data, indent=2) + "\n")
        shared[name]["volumes"] = [path + ":" + target + ":ro"]

    # Preserve the existing Postgres major version, volume, DBs, Keycloak realms
    # and credentials. DB initialization is a separate, explicit command.
    shared["postgres"]["volumes"] = ["postgres-data:/var/lib/postgresql/data"]
    shared["postgres"]["command"] = ["postgres", "-c", "max_connections=700"]
    shared["postgres"]["ports"] = ["5432:5432"]
    shared["redis"]["ports"] = ["6379:6379"]
    shared["keycloak"]["command"] = ["start-dev"]
    shared["keycloak"].pop("volumes", None)
    shared["keycloak"]["depends_on"] = {"postgres": {"condition": "service_healthy"}}
    shared["keycloak"]["environment"].update({
        "KC_DB": "postgres", "KC_DB_URL": "jdbc:postgresql://postgres:5432/keycloak",
        "KC_DB_USERNAME": "keycloak_user", "KC_DB_PASSWORD": "${KEYCLOAK_DB_PASSWORD:-keycloak_pass}",
        "KC_HOSTNAME": KC, "KC_HTTP_ENABLED": "true", "KC_HEALTH_ENABLED": "true",
        "JAVA_OPTS_KC_HEAP": "-XX:MaxRAMPercentage=15 -XX:InitialRAMPercentage=5",
    })
    shared["keycloak"]["ports"] = ["8080:8080"]
    shared["minio"]["ports"] = ["9100:9000", "9101:9001"]
    shared["minio-init"]["profiles"] = ["setup"]
    shared["keycloak-init"]["profiles"] = ["setup"]
    shared["iam-staff-api"]["depends_on"].pop("keycloak-init", None)
    shared["awe"]["depends_on"].pop("keycloak-init", None)
    for name, port in (("iam-staff-api", 8100), ("awe", 8130), ("farmer-master-data-api", 8110)):
        shared[name]["ports"] = [f"{port}:8000"]
    shared["awe-ui"]["ports"] = ["8131:8080"]
    shared["awe-ui"]["healthcheck"] = {
        "test": ["CMD", "wget", "-q", "--spider", "http://127.0.0.1:8080/"],
        "interval": "10s", "timeout": "5s", "retries": 12,
    }
    shared["awe"]["environment"].update({"AWE__KEYCLOAK__REALM": "farmer", "AWE__KEYCLOAK__BASE_URL": KC})
    shared["iam-staff-api"]["environment"].update({
        "IAM_STAFF_KEYCLOAK_BASE_URL": KC, "IAM_STAFF_KEYCLOAK_ISSUER_URL": ISSUER,
        "IAM_STAFF_KEYCLOAK_REALM": "farmer", "IAM_STAFF_CSRF_ENABLED": "true",
        "IAM_STAFF_DATA_APPLICATION_URLS__KEYCLOAK_APPLICATION_URL": KC,
        "IAM_STAFF_DATA_APPLICATION_URLS__REGISTRY_APPLICATION_URL": PORTAL,
        "IAM_STAFF_DATA_APPLICATION_URLS__MINIO_APPLICATION_URL": "http://minio.farmer.localtest.me:9101",
    })
    shared["farmer-master-data-api"]["environment"].update({
        "MASTER_DATA_API_AUTH_ENABLED": "true", "MASTER_DATA_API_CSRF_ENABLED": "true",
        "MASTER_DATA_API_KEYCLOAK_CLIENT_ID": "master-data", "MASTER_DATA_API_NO_OF_WORKERS": "1",
    })
    shared["staff-portal"] = {
        "image": "openg2p/openg2p-staff-portal-ui:1.2.0", "ports": ["3102:3000"],
        "environment": {"HOSTNAME": "0.0.0.0", "IAM_URL": IAM, "LOGIN_PROVIDER_ID": "1",
                        "COOKIE_DOMAIN": "farmer.localtest.me"},
        "extra_hosts": ["iam.farmer.localtest.me:host-gateway"], "restart": "unless-stopped",
        "entrypoint": ["node", "/local-http.js"],
        "volumes": [HERE.as_posix() + "/staff-portal-http.js:/local-http.js:ro"],
    }
    # Keep mail used by the other registries in the shared project too.
    shared["mailpit"] = {
        "image": "axllent/mailpit:latest", "container_name": "openg2p-shared-mailpit",
        "ports": ["8025:8025", "1025:1025"], "restart": "unless-stopped",
    }

    init = (ROOT / "docker/local-dev/keycloak-init.sh").read_text(encoding="utf-8")
    # This source uses both shell quoting styles for port interpolation.
    for var, host in (("IAM_STAFF_PORT", "iam.farmer.localtest.me"),
                      ("FARMER_REGISTRY_UI_PORT", "portal.farmer.localtest.me"),
                      ("AWE_UI_PORT", "awe.farmer.localtest.me")):
        init = re.sub(r"localhost:(['\"]*)\$\{" + var + r"\}", host + r":\1${" + var + "}", init)
    init += "\n" + (HERE / "keycloak-commons.sh").read_text(encoding="utf-8")
    write(out / "keycloak-init.sh", init)
    shared["keycloak-init"]["volumes"] = [(out / "keycloak-init.sh").as_posix() + ":/keycloak-init.sh:ro"]
    shared["keycloak-init"]["environment"].update({
        "KEYCLOAK_REALM": "farmer", "IAM_STAFF_PORT": "8100",
        "FARMER_REGISTRY_UI_PORT": "3100", "AWE_UI_PORT": "8131",
        "COMMONS_CLIENT_SECRET": "${COMMONS_CLIENT_SECRET:-dev-commons-client-secret}",
    })
    write(out / "farmer-catalog.json", (ROOT / "local/iam-register/payload.json").read_text(encoding="utf-8"))
    shared["sync-login-provider"] = {
        "image": PINS["iam-staff-api"], "profiles": ["setup"],
        "entrypoint": ["python", "/setup/sync_login_provider.py"],
        "environment": copy.deepcopy(shared["iam-staff-api"]["environment"]),
        "volumes": [HERE.as_posix() + ":/setup:ro"],
    }
    shared["register-apps"] = {
        "image": PINS["iam-staff-api"], "profiles": ["setup"],
        "entrypoint": ["python", "/setup/register_apps.py"],
        "environment": {"COMMONS_CLIENT_SECRET": "${COMMONS_CLIENT_SECRET:-dev-commons-client-secret}"},
        "extra_hosts": ["keycloak.localtest.me:host-gateway"],
        "volumes": [HERE.as_posix() + ":/setup:ro"],
    }

    for name, port in (("id-generator", 8140), ("farmer-registry-staff-api", 8101),
                       ("farmer-registry-partner-api", 8102)):
        farmer[name]["ports"] = [f"{port}:8000"]
    farmer["farmer-registry-staff-ui"]["ports"] = ["3100:3000"]
    farmer["farmer-registry-staff-ui"]["environment"].update({
        "IAM_URL": IAM, "REDIRECT_URL": PORTAL,
        "CSP_HEADER": source["farmer-registry-staff-ui"]["environment"]["CSP_HEADER"].replace("minio.localtest.me:9000", MINIO),
    })
    # Shared Redis holds IAM sessions; a separate registry queue is owned by
    # Farmer. Stopping Farmer must never stop the shared authentication cache.
    farmer["queue"] = {"image": "redis:7-alpine", "restart": "unless-stopped",
                       "command": ["redis-server", "--appendonly", "yes"], "volumes": ["queue-data:/data"],
                       "healthcheck": {"test": ["CMD", "redis-cli", "ping"], "interval": "5s", "timeout": "3s", "retries": 10}}
    for name in ("farmer-registry-celery-worker", "farmer-registry-celery-beat"):
        env = farmer[name]["environment"]
        for key in env:
            if "CELERY_BROKER_URL" in key or "CELERY_BACKEND_URL" in key:
                env[key] = "redis://queue:6379/0"
        farmer[name]["depends_on"]["queue"] = {"condition": "service_healthy"}
    for name, prefix in (("farmer-registry-staff-api", "REGISTRY_STAFF_PORTAL_API_"),
                         ("farmer-registry-partner-api", "REGISTRY_PARTNER_API_"),
                         ("farmer-registry-celery-worker", "REGISTRY_CELERY_WORKERS_")):
        env = farmer[name]["environment"]
        env.update({prefix + "MASTER_DATA_API_URL": "http://farmer-master-data-api:8000",
                    prefix + "MASTER_DATA_TOKEN_URL": ISSUER + "/protocol/openid-connect/token",
                    prefix + "MASTER_DATA_CLIENT_ID": "commons-services-staff-portal",
                    prefix + "MASTER_DATA_CLIENT_SECRET": "${COMMONS_CLIENT_SECRET:-dev-commons-client-secret}",
                    prefix + "PARTNER_MGMT_API_URL": "http://pm-partner-api:8000",
                    prefix + "PARTNER_MGMT_ADMIN_API_URL": "http://pm-staff-api:8000",
                    prefix + "PARTNER_MGMT_ADMIN_TOKEN_URL": ISSUER + "/protocol/openid-connect/token",
                    prefix + "PARTNER_MGMT_ADMIN_CLIENT_ID": "commons-services-staff-portal",
                    prefix + "PARTNER_MGMT_ADMIN_CLIENT_SECRET": "${COMMONS_CLIENT_SECRET:-dev-commons-client-secret}"})
        if name != "farmer-registry-celery-worker":
            env[prefix + "AUDIT_ENABLED"] = "${AUDIT_ENABLED:-false}"
            env[prefix + "AUDIT_MANAGER_URL"] = "http://audit-manager:8000"
    farmer["farmer-registry-staff-api"]["environment"].update({
        "REGISTRY_STAFF_PORTAL_API_AUTH_ENABLED": "true", "REGISTRY_STAFF_PORTAL_API_CSRF_ENABLED": "true",
        "STAFF_PORTAL_NO_OF_WORKERS": "1",
    })
    farmer["farmer-registry-celery-worker"]["environment"]["CELERY_OPTS"] = "worker -Q farmer_registry_worker_queue --loglevel=info --concurrency=2"
    farmer["farmer-registry-celery-beat"]["environment"]["CELERY_OPTS"] = "worker --beat -Q celery --loglevel=info --concurrency=1 --schedule=/tmp/celery-beat-schedule.db"
    farmer["farmer-registry-partner-api"]["environment"].update({
        "PARTNER_NO_OF_WORKERS": "1",
        "REGISTRY_PARTNER_API_SIGNATURE_VALIDATION_ENABLED": "true",
        "REGISTRY_PARTNER_API_CONSENT_ENFORCEMENT_ENABLED": "true",
        "REGISTRY_PARTNER_API_CRYPTO_BACKEND": "partner-mgmt",
        "REGISTRY_PARTNER_API_CONSENT_MANAGER_URL": "http://cm-partner-api:8000",
    })
    seed = farmer["farmer-registry-db-seed"]
    seed["profiles"] = ["seed"]
    seed["environment"].update({"LOAD_GEO_DATA": "false", "LOAD_SAMPLE_DATA": "false",
                                "LOAD_IMAGES": "false", "SYNC_GEO_WIDGETS": "true"})
    # Resolve external dependencies before any new image's migration entrypoint.
    gate_env = copy.deepcopy(farmer["farmer-registry-staff-api"]["environment"])
    farmer["preflight"] = {
        "image": "farmer-gen2-local/staff-api:dev", "pull_policy": "never", "profiles": ["check"],
        "entrypoint": ["python", "/checks/preflight.py"],
        "extra_hosts": ["keycloak.localtest.me:host-gateway", "minio.farmer.localtest.me:host-gateway"],
        "volumes": [HERE.as_posix() + ":/checks:ro", (ROOT / "ci/gen2").as_posix() + ":/schema-checks:ro"],
        "environment": {**gate_env, "PYTHONPATH": "/schema-checks"},
    }
    farmer["registry-dashboard-api"] = {
        "image": "${DASHBOARD_API_IMAGE:-openg2p-local/farmer-registry-dashboard-api:dev}",
        "profiles": ["reporting"], "ports": ["127.0.0.1:8105:8000"],
        "environment": {"DATABASE_URL": "postgresql://postgres@postgres:5432/farmer_registry_db",
                        "PGPASSWORD": PASSWORD, "DB_POOL_MAX_SIZE": "3", "ALLOWED_ORIGINS": "[]",
                        "AUTH_IAM_URL": "http://iam-staff-api:8000"},
        "extra_hosts": ["keycloak.localtest.me:host-gateway"], "restart": "unless-stopped",
    }
    farmer["reporting-views"] = {
        "image": "farmer-gen2-local/db-seed:dev", "profiles": ["reporting-seed"], "pull_policy": "never",
        "entrypoint": ["sh", "-ec", "psql -v ON_ERROR_STOP=1 -f /seed/reporting_views.sql; sh /seed/reporting_geo_levels.sh"],
        "environment": {"PGHOST": "postgres", "PGPORT": "5432", "PGDATABASE": "farmer_registry_db",
                        "PGUSER": "${POSTGRES_SUPERUSER:-postgres}", "PGPASSWORD": PASSWORD,
                        "REPORTING_PREFIX": "fr_rpt_", "REPORTING_CONFIG": "/seed/reporting.yaml",
                        "MDS_DB": "farmer_master_data_db", "MDS_PGPORT": "5432",
                        "MDS_PGUSER": "${POSTGRES_SUPERUSER:-postgres}", "MDS_PGPASSWORD": PASSWORD},
    }
    extra = yaml.safe_load((HERE / "commons-services.yaml").read_text(encoding="utf-8"))
    shared.update(extra["services"])
    for service in shared.values():
        # Explicit shared network permits AWE callbacks into Farmer. It is
        # external so `down` on either project cannot delete the other side.
        service.setdefault("networks", ["default"])
        service.setdefault("extra_hosts", ["keycloak.localtest.me:host-gateway", "iam.farmer.localtest.me:host-gateway"])
        mounts = service.get("volumes", [])
        for i, mount in enumerate(mounts):
            if mount.startswith("./"):
                path, target = mount.split(":", 1)
                mounts[i] = (HERE / path).as_posix() + ":" + target
    network = {"default": {"external": True, "name": "openg2p-gen2"}}
    shared_doc = {"name": "openg2p-shared", "services": shared, "networks": network,
                  "volumes": {"postgres-data": {"external": True, "name": "openg2p-shared_postgres-data"},
                              "minio-data": {"external": True, "name": "farmer-registry_minio-data"},
                              "kafka-data": {}}}
    farmer_doc = {"name": "farmer-registry", "services": farmer, "networks": network, "volumes": {"queue-data": {}}}
    for name, doc in (("shared", shared_doc), ("farmer", farmer_doc)):
        write(out / (name + ".compose.json"), json.dumps(doc, indent=2) + "\n")
    return shared_doc, farmer_doc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "generated")
    args = parser.parse_args()
    render(args.output)
    print(f"Rendered independent shared/Farmer projects in {args.output}")
