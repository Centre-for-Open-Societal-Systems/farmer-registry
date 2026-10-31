"""Staging must reject stale rehearsal, wrong resources and premature ingestion."""
import copy
import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
import re
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


staging = module("staging_gate", "ci/deploy/staging.py")
deployment = module("staging_deployment", "ci/deploy/deployment.py")
delivery = module("staging_environment", "ci/environments.py")
handoff = module("staging_handoff", "scripts/operations/connector/release_handoff.py")
cutover = module("staging_cutover", "scripts/operations/connector/connector_cutover.py")
schema = module("staging_schema", "scripts/operations/commons/check_geo_schema.py")
identity = module("staging_identity", "scripts/operations/identity/check.py")
NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
SHA = "a" * 40
ECR = "123456789012.dkr.ecr.ap-south-1.amazonaws.com"
DIGEST = "sha256:" + "b" * 64


@pytest.fixture
def evidence(monkeypatch):
    monkeypatch.setattr(staging, "delivery_hash", lambda: "c" * 64)
    images = {}
    for name in ("staff-api", "staff-ui", "partner-api", "celery", "db-seed", "sanity-tests"):
        commit = "d" * 40 if name == "partner-api" else SHA
        images[name] = {"repository": ECR + "/openg2p/farmer-registry/" + name,
                        "tag": commit[:12], "sourceCommit": commit, "digest": DIGEST, "runtimeTested": True}
    return {"environment": "staging", "namespace": "far", "platform": "1.2.2-rc.544",
            "deliveryHash": "c" * 64, "verifiedAt": NOW.isoformat(), "finalBackupAt": NOW.isoformat(),
            "baselineRevision": 36, "valuesHash": "e" * 64, "manifestHash": "f" * 64,
            "candidateManifestHash": "1" * 64,
            "rehearsal": dict.fromkeys(staging.REHEARSAL, True),
            "cutover": dict.fromkeys(staging.CUTOVER, True),
            "backups": dict.fromkeys(("registry", "connector", "helm", "odkFormMedia", "pipelines", "runHistory", "checkpoints"), "2" * 64),
            "registry": {"registry": ECR, "sourceCommit": SHA, "images": images}}


@pytest.fixture
def oan_evidence(evidence):
    """Evidence of the OAN install in namespace farmer: no baseline release, so no baseline fields."""
    record = copy.deepcopy(evidence)
    record.update(namespace="farmer", platform=staging.pinned_platform())
    for field in staging.BASELINE_FIELDS:
        del record[field]
    return record


def verify(tmp_path, record, now=NOW):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(record))
    return staging.evidence(path, SHA, now)


def test_tested_image_set_can_preserve_independently_accepted_partner_commit(tmp_path, evidence):
    record = verify(tmp_path, evidence)
    assert record["registry"]["images"]["partner-api"]["sourceCommit"] != SHA


def test_safe_promotion_record_does_not_export_unknown_private_fields(tmp_path, evidence):
    evidence["registry"]["operatorPassword"] = "synthetic-private-value"
    evidence["registry"]["images"]["celery"]["operatorToken"] = "synthetic-private-value"
    record = verify(tmp_path, evidence)
    assert "synthetic-private-value" not in json.dumps(record["registry"])


def test_actual_cli_rejects_unverified_template_and_accepts_recorded_staging_status(tmp_path, oan_evidence):
    path, status = tmp_path / "rehearsal.json", tmp_path / "status.json"
    created = subprocess.run([sys.executable, str(ROOT / "ci/deploy/staging.py"), "template", str(path)], capture_output=True, text=True)
    assert created.returncode == 0
    template = json.loads(path.read_text())
    assert template["namespace"] == "farmer" and template["platform"] == "1.2.2-rc.614"
    assert not set(staging.BASELINE_FIELDS) & set(template)
    status.write_text(json.dumps({"name": "farmer-registry", "namespace": "farmer", "version": 3, "info": {"status": "deployed"}}))
    env = dict(os.environ, DELIVERY_ENVIRONMENT="staging", STAGING_EVIDENCE_FILE=str(path), SOURCE_COMMIT=SHA)
    command = [sys.executable, str(ROOT / "ci/deploy/deployment.py"), "upgrade-mode", str(status)]
    assert subprocess.run(command, env=env, capture_output=True, text=True).returncode == 1
    oan_evidence.update(deliveryHash=template["deliveryHash"], verifiedAt=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(oan_evidence))
    accepted = subprocess.run(command, env=env, capture_output=True, text=True)
    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout.strip() == "normal"


def test_oan_evidence_reads_the_platform_from_the_pin_and_needs_no_baseline(tmp_path, oan_evidence):
    assert staging.pinned_platform() == "1.2.2-rc.614"
    record = verify(tmp_path, oan_evidence)
    assert not set(staging.BASELINE_FIELDS) & set(record)
    assert record["registry"]["images"]["staff-api"]["digest"] == DIGEST


@pytest.mark.parametrize("field,value", [("platform", "1.2.2-rc.544"), ("platform", "0.0.0"), ("namespace", "far"),
    ("namespace", "commons"), ("environment", "dev"), ("deliveryHash", "0" * 64)])
def test_oan_evidence_rejects_other_platform_namespace_environment_or_delivery(tmp_path, oan_evidence, field, value):
    oan_evidence[field] = value
    with pytest.raises(ValueError):
        verify(tmp_path, oan_evidence)


@pytest.mark.parametrize("hours", [-1, 25])
def test_oan_evidence_keeps_the_freshness_rule(tmp_path, oan_evidence, hours):
    with pytest.raises(ValueError):
        verify(tmp_path, oan_evidence, NOW + timedelta(hours=hours))


def test_oan_evidence_keeps_image_digests_and_backup_hashes(tmp_path, oan_evidence):
    oan_evidence["registry"]["images"]["celery"]["digest"] = "latest"
    with pytest.raises(ValueError):
        verify(tmp_path, oan_evidence)
    oan_evidence["registry"]["images"]["celery"]["digest"] = DIGEST
    oan_evidence["backups"]["registry"] = "short"
    with pytest.raises(ValueError):
        verify(tmp_path, oan_evidence)


def test_oan_cutover_needs_maintenance_a_fresh_final_backup_and_the_oan_release(tmp_path, oan_evidence):
    record = verify(tmp_path, oan_evidence)
    status = {"name": "farmer-registry", "namespace": "farmer", "version": 1, "info": {"status": "deployed"}}
    values = {"global": {"registryDB": "farmer_registry"}}
    staging.cutover(record, status, values, [], NOW)
    with pytest.raises(ValueError, match="Fresh"):
        staging.cutover(record, status, values, [], NOW + timedelta(hours=2))
    with pytest.raises(ValueError, match="OAN release"):
        staging.cutover(record, dict(status, namespace="far"), values, [], NOW)
    with pytest.raises(ValueError, match="database"):
        staging.cutover(record, status, {"global": {"registryDB": "farmer_registry_far"}}, [], NOW)


def test_duplicate_environment_entries_cannot_hide_disabled_verification():
    doc = workload("Deployment", "partner-api", "fixture")
    container = deployment.pod(doc)["containers"][0]
    container["env"] = [{"name": "SIGNATURE_VALIDATION", "value": value} for value in ("true", "false")]
    with pytest.raises(ValueError, match="Duplicate"): deployment.envs(doc)


@pytest.mark.parametrize("field,value", [("environment", "dev"), ("namespace", "farmer"),
    ("platform", "0.0.0-develop.384"), ("deliveryHash", "0" * 64),
    ("baselineRevision", True), ("candidateManifestHash", ""), ("valuesHash", "")])
def test_evidence_cannot_cover_other_delivery_or_unreviewed_content(tmp_path, evidence, field, value):
    evidence[field] = value
    with pytest.raises(ValueError): verify(tmp_path, evidence)


@pytest.mark.parametrize("hours", [-1, 25])
def test_future_and_stale_rehearsal_are_rejected(tmp_path, evidence, hours):
    with pytest.raises(ValueError): verify(tmp_path, evidence, NOW + timedelta(hours=hours))


@pytest.mark.parametrize("check", staging.REHEARSAL)
def test_each_rehearsal_guarantee_is_required(tmp_path, evidence, check):
    evidence["rehearsal"][check] = False
    with pytest.raises(ValueError): verify(tmp_path, evidence)


@pytest.mark.parametrize("field,value", [("digest", "latest"), ("tag", "staging"),
    ("sourceCommit", "develop"), ("runtimeTested", False), ("repository", ECR + "/other/partner-api")])
def test_image_provenance_must_be_complete_and_immutable(tmp_path, evidence, field, value):
    evidence["registry"]["images"]["partner-api"][field] = value
    with pytest.raises(ValueError): verify(tmp_path, evidence)


def test_missing_dump_or_image_is_rejected(tmp_path, evidence):
    del evidence["backups"]["runHistory"]
    with pytest.raises(ValueError): verify(tmp_path, evidence)
    evidence["backups"]["runHistory"] = "2" * 64
    del evidence["registry"]["images"]["sanity-tests"]
    with pytest.raises(ValueError): verify(tmp_path, evidence)


@pytest.fixture
def baseline(evidence):
    values = {"global": {"registryHostname": "farmer-registry.oanstaging.com", "registryDB": "farmer_registry_far"}}
    manifest = [{"kind": "Service", "metadata": {"name": "farmer-registry", "namespace": "far"}, "spec": {"ports": [80]}}]
    status = {"name": "farmer-registry", "namespace": "far", "version": 36, "info": {"status": "deployed"}}
    evidence.update(valuesHash=staging.content_hash(values), manifestHash=staging.content_hash(manifest))
    return status, values, manifest


def test_final_backup_is_bound_to_current_installed_values_and_revision(evidence, baseline):
    staging.cutover(evidence, *baseline, NOW)
    baseline[0]["version"] = 37
    with pytest.raises(ValueError, match="changed"): staging.cutover(evidence, *baseline, NOW)


@pytest.mark.parametrize("check", staging.CUTOVER)
def test_no_deploy_before_final_backup_and_maintenance(evidence, baseline, check):
    evidence["cutover"][check] = False
    with pytest.raises(ValueError): staging.cutover(evidence, *baseline, NOW)


def test_old_final_backup_and_configuration_drift_are_rejected(evidence, baseline):
    with pytest.raises(ValueError, match="Fresh"): staging.cutover(evidence, *baseline, NOW + timedelta(hours=2))
    baseline[1]["global"]["registryDB"] = "farmer_registry"
    with pytest.raises(ValueError): staging.cutover(evidence, *baseline, NOW)


@pytest.mark.parametrize("environment", ["dev", "staging"])
def test_credential_namespace_server_and_connector_resources_are_paired(environment):
    config = delivery.configuration(environment)
    context = {"clusters": [{"cluster": {"server": config["apiServers"][0]}}]}
    delivery.validate_cluster(environment, config["kubeconfigCredential"], context)
    other = delivery.configuration("dev" if environment == "staging" else "staging")
    with pytest.raises(ValueError): delivery.validate_cluster(environment, other["kubeconfigCredential"], context)
    context["clusters"][0]["cluster"]["server"] = other["apiServers"][0]
    with pytest.raises(ValueError): delivery.validate_cluster(environment, config["kubeconfigCredential"], context)
    settings = {"namespace": config["namespace"], "database": config["connectorDatabase"], "queue": config["connectorQueue"]}
    delivery.connector_settings(environment, settings)
    for field, wrong in (("namespace", "far"), ("database", other["connectorDatabase"] + "_other"), ("queue", other["connectorQueue"] + "-other")):
        with pytest.raises(ValueError): delivery.connector_settings(environment, dict(settings, **{field: wrong}))


def workload(kind, suffix, image):
    return {"kind": kind, "metadata": {"name": "farmer-registry-" + suffix, "namespace": "farmer"},
            "spec": {"selector": {"matchLabels": {"app": suffix}}, "template": {"spec": {
                "containers": [{"name": "app", "image": image, "env": []}]}}}}


def release_manifests(evidence):
    before, after = [], []
    images = evidence["registry"]["images"]
    for _, (kind, suffix, name) in deployment.COMPONENTS.items():
        old = workload(kind, suffix, images[name]["repository"] + ":" + "0" * 12)
        before.append(old)
        new = copy.deepcopy(old)
        container = deployment.pod(new)["containers"][0]
        container["image"] = images[name]["repository"] + ":" + images[name]["tag"] + "@" + DIGEST
        rendered = {**deployment.identity_env(suffix, "staging"), **deployment.location_env(suffix, "staging"), **deployment.outgestion_env(suffix, "staging")}
        container["env"] = [deployment.env_entry(k, v) for k, v in rendered.items()]
        after.append(new)
    return before, after, images


def test_registry_staging_upgrade_pins_all_digests_and_enforces_signing(evidence):
    before, after, images = release_manifests(evidence)
    deployment.validate(before, after, ECR, SHA[:12], environment="staging", images=images)
    partner = next(d for d in after if d["metadata"]["name"].endswith("-partner-api"))
    env = deployment.pod(partner)["containers"][0]["env"]
    env[:] = [v for v in env if v["name"] != "REGISTRY_PARTNER_API_SIGNATURE_VALIDATION_ENABLED"]
    with pytest.raises(ValueError, match="signature"): deployment.validate(before, after, ECR, SHA[:12], environment="staging", images=images)


@pytest.mark.parametrize("fault", [None, "missing", "wrong-image", "changed-env"])
def test_optional_public_ui_must_survive_with_its_config_and_accepted_image(evidence, fault):
    before, after, images = release_manifests(evidence)
    old = workload("Deployment", "staff-portal-ui-public", images["staff-ui"]["repository"] + ":" + "0" * 12)
    deployment.pod(old)["containers"][0]["env"] = [{"name": "COOKIE_DOMAIN", "value": ".oanstaging.com"}]
    before.append(old)
    new = copy.deepcopy(old)
    deployment.pod(new)["containers"][0]["image"] = images["staff-ui"]["repository"] + ":" + images["staff-ui"]["tag"] + "@" + DIGEST
    if fault != "missing": after.append(new)
    if fault == "wrong-image": deployment.pod(new)["containers"][0]["image"] = "previous"
    if fault == "changed-env": deployment.pod(new)["containers"][0]["env"] = []
    if fault:
        with pytest.raises(ValueError): deployment.validate(before, after, ECR, SHA[:12], environment="staging", images=images)
    else:
        deployment.validate(before, after, ECR, SHA[:12], environment="staging", images=images)


def test_preparation_preserves_staging_database_and_awe_callback(evidence):
    values = {"global": {"registryHostname": "farmer-registry.oanstaging.com", "registryDB": "farmer_registry_far", "aweDefaultCallbackUrl": "http://existing/awe/webhooks/decision"}}
    before = [workload("Deployment", "staff-portal-api", "previous")]
    result = deployment.prepare(values, before, ECR, SHA[:12], environment="staging", images=evidence["registry"]["images"])
    assert result["global"]["registryDB"] == "farmer_registry_far"
    assert result["global"]["aweDefaultCallbackUrl"] == values["global"]["aweDefaultCallbackUrl"]
    assert result["registry"]["partnerApi"]["image"]["tag"] == "d" * 12 + "@" + DIGEST
    assert "keycloakIssuerUrl" not in values["global"]
    with pytest.raises(ValueError): deployment.prepare(values, before, ECR, SHA[:12], environment="dev")


def test_staging_fresh_install_prepares_from_environment_values_with_digests_and_no_demo_data(evidence):
    images = evidence["registry"]["images"]
    values = {"global": {"registryHostname": "farmer-registry.oanstaging.com"}}
    prepared = deployment.prepare(values, [], ECR, SHA[:12], environment="staging", images=images, fresh=True)
    assert prepared["registry"]["staffApi"]["image"]["tag"] == SHA[:12] + "@" + DIGEST
    seed = prepared["registry"]["dbSeed"]
    assert seed["loadSampleData"] is False and seed["loadGeoData"] is False and seed["loadImages"] is False
    assert seed["intakeSeed"]["enabled"] is False
    assert prepared["global"]["keycloakIssuerUrl"] == "https://keycloak.oanstaging.com/realms/staff"
    assert prepared["registrantAuth"]["esignetBaseUrl"] == "https://esignet.oanstaging.com"
    assert "development" not in yaml.safe_dump(prepared)
    with pytest.raises(ValueError):
        deployment.prepare(values, [workload("Deployment", "staff-portal-api", "x")], ECR, SHA[:12], environment="staging", images=images, fresh=True)
    with pytest.raises(ValueError):
        deployment.prepare(values, [], ECR, SHA[:12], environment="staging", images=images)
    with pytest.raises(ValueError):
        deployment.prepare({"global": {"registryHostname": "other.example"}}, [], ECR, SHA[:12], environment="staging", images=images, fresh=True)
    with pytest.raises(ValueError):
        deployment.prepare(values, [], ECR, SHA[:12], environment="staging", fresh=True)


def test_persistent_manifest_hash_binds_storage_config_and_routes(baseline):
    manifest = baseline[2]
    expected = staging.manifest_hash(manifest)
    assert staging.manifest_hash(list(reversed(manifest))) == expected
    manifest[0]["spec"]["ports"] = [443]
    assert staging.manifest_hash(manifest) != expected


def test_staging_connector_values_never_start_ingestion():
    values = yaml.safe_load((ROOT / "helm/environments/staging/services/registry-connector.yaml").read_text(encoding="utf-8"))
    delivery.connector_settings("staging", values["_coordination"])
    assert values["cossQueue"] == "farmer-registry-connector-v2"
    assert values["cossSigning"] == {"enabled": True, "partnerId": "farmer-partner",
        "keyId": "farmer-connector-v2-staging", "secret": "farmer-connector-v2-staging-signing"}
    assert values["global"]["connectorDB"] == "farmer_connector_v2"
    assert values["global"]["connectorDBSecret"] == "farmer-connector-v2-staging-db"
    assert values["global"]["hostname"] == "connector-farmer-registry.oanstaging.com"
    assert values["adminAuth"]["issuer"] == "https://keycloak.oanstaging.com/realms/staff"
    assert all(values[role]["replicaCount"] == 0 for role in ("api", "worker", "ui"))
    assert values["beat"]["enabled"] is False and values["consumer"]["enabled"] is False
    assert "development" not in yaml.safe_dump(values) and not re.search(r"[-_]far(?!mer)", yaml.safe_dump(values))


def test_staging_scheduler_needs_manual_intake_and_real_submission_acceptance(tmp_path):
    with pytest.raises(ValueError): handoff.activate_scheduler(tmp_path / "uncreated", {}, "staging")
    assert not (tmp_path / "uncreated").exists()


def test_staging_backups_cannot_be_reused_as_dev(tmp_path):
    exports = {name: "2" * 64 for name in ("values.yaml", "manifest.yaml", "hooks.yaml", "pipelines.json", "mappings.json", "checkpoints.json", "database.dump")}
    (tmp_path / "backup.json").write_text(json.dumps({"release": "farmer-connector", "namespace": "far", "files": exports}))
    with pytest.raises(cutover.ServiceError, match="incomplete-backup"): cutover.verify_backup(tmp_path, "dev")


@pytest.mark.parametrize("fault", [None, "missing-beat", "two-beats", "wrong-ui-digest", "dev-signing-key", "unsigned-unverified"])
def test_staging_retirement_requires_both_accepted_images_one_scheduler_and_negative_cases(fault):
    env = [{"name": key, "value": value} for key, value in {
        "CONNECTOR_REQUIRE_SIGNING": "true", "CONNECTOR_SIGNING_ENABLED": "true",
        "CONNECTOR_SIGNING_ALGORITHM": "RS256", "CONNECTOR_SIGNING_ISSUER": "farmer-partner",
        "CONNECTOR_SIGNING_KEY_ID": "farmer-connector-v2-staging",
        "CONNECTOR_CELERY_QUEUE": "farmer-registry-connector-v2",
        "CONNECTOR_DB_DBNAME": "farmer_connector_v2", "CONNECTOR_DB_USERNAME": "farmer_connector_v2_user",
    }.items()]
    env.extend({"name": key, "valueFrom": {"secretKeyRef": {"name": name, "key": field}}} for key, name, field in (
        ("CONNECTOR_SIGNING_PRIVATE_KEY_PEM", "farmer-connector-v2-staging-signing", "private-key.pem"),
        ("CONNECTOR_DB_PASSWORD", "farmer-connector-v2-staging-db", "password")))
    new = [{"kind": "Deployment", "metadata": {"name": cutover.NEW + "-" + role, "namespace": "farmer"},
            "spec": {"replicas": 1, "template": {"spec": {"containers": [
                {"name": "app", "image": "fixture/" + role + "@" + DIGEST, "env": [] if role == "ui" else copy.deepcopy(env)}]}}}}
           for role in ("api", "worker", "ui", "beat")]
    status = {"name": cutover.NEW, "namespace": "farmer", "version": 7, "info": {"status": "deployed"}}
    review = dict.fromkeys((*cutover.ACCEPTANCE, *staging.ACCEPTANCE), True)
    review.update(environment="staging", backupHash="fixture", helmRevision=7, digest=DIGEST, images={"api": DIGEST, "ui": DIGEST})
    if fault == "missing-beat": new.pop()
    if fault == "two-beats": new[-1]["spec"]["replicas"] = 2
    if fault == "wrong-ui-digest": deployment.pod(new[2])["containers"][0]["image"] = "fixture/ui@sha256:" + "d" * 64
    if fault == "dev-signing-key":
        for item in deployment.pod(new[0])["containers"][0]["env"]:
            if item["name"] == "CONNECTOR_SIGNING_KEY_ID": item["value"] = "farmer-connector-v2-52da0fc34e90"
    if fault == "unsigned-unverified": review["unsignedRejected"] = False
    if fault:
        with pytest.raises((ValueError, cutover.ServiceError)): cutover.retirement_guard([], [], status, new, review, "fixture", "staging")
    else:
        cutover.retirement_guard([], [], status, new, review, "fixture", "staging")


@pytest.mark.parametrize("fault", [None, "missing-column", "wrong-table", "text", "nullable-document"])
def test_schema_requires_all_36_specific_coordinates_and_document_history(monkeypatch, fault):
    rows = [{"table_name": f"g2p_{prefix}{table}", "column_name": column, "data_type": "double precision"}
            for prefix in ("register_", "register_history_", "intake_form_")
            for table in ("farmers", "households", "household_members", "lands")
            for column in ("latitude", "longitude", "altitude")]
    if fault == "missing-column": rows.pop()
    if fault == "wrong-table": rows[-1]["table_name"] = "other"
    if fault == "text": rows[-1]["data_type"] = "text"
    class Connection:
        def transaction(self, readonly):
            assert readonly is True
            return self
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def fetch(self, query):
            if query == schema.QUERY: return rows
            assert query == schema.DOCUMENT_QUERY
            return [{"data_type": "text", "is_nullable": "YES" if fault == "nullable-document" else "NO"}]
        async def close(self): pass
    async def connect(**kwargs): return Connection()
    monkeypatch.setitem(sys.modules, "asyncpg", SimpleNamespace(connect=connect))
    for key in ("HOSTNAME", "DBNAME", "USERNAME", "PASSWORD"):
        monkeypatch.setenv("REGISTRY_STAFF_PORTAL_API_DB_" + key, "synthetic")
    assert asyncio.run(schema.check()) == (1 if fault else 0)


@pytest.mark.parametrize("fault", [None, "dev-issuer", "other-realm-jwks", "dev-review", "different-key"])
def test_staging_identity_requires_public_staff_issuer_and_matching_internal_keys(fault):
    issuer, iam, _ = identity.environment_settings("staging")
    endpoints = {name: issuer + "/protocol/openid-connect/" + suffix for name, suffix in (
        ("authorization_endpoint", "auth"), ("token_endpoint", "token"), ("userinfo_endpoint", "userinfo"))}
    provider = dict(endpoints, id=1, active=True, issuer=issuer,
                    server_metadata_url=issuer + "/.well-known/openid-configuration", oauth_callback_url=iam + "/auth/callback")
    awe = {"awe": {"keycloak": {"issuer": issuer, "realm": "staff", "audience": "farmer-staff",
           "base_url": issuer.removesuffix("/realms/staff"),
           "jwks_url": "http://commons-keycloak:80/realms/staff/protocol/openid-connect/certs"}}}
    public = {"keys": [{"kty": "RSA", "kid": "fixture", "n": "public-material", "e": "AQAB"}]}
    internal = copy.deepcopy(public)
    review = dict.fromkeys(identity.CHECKS, True)
    review.update(environment="staging", issuer=issuer, aweAudience="farmer-staff")
    if fault == "dev-issuer": provider["issuer"] = identity.ISSUER
    if fault == "other-realm-jwks": awe["awe"]["keycloak"]["jwks_url"] = "http://commons-keycloak:80/realms/master/protocol/openid-connect/certs"
    if fault == "dev-review": review["environment"] = "dev"
    if fault == "different-key": internal["keys"][0]["n"] = "wrong-material"
    args = (provider, awe, dict(endpoints, issuer=issuer), public, internal, review)
    if fault:
        with pytest.raises(ValueError): identity.check(*args, environment="staging")
    else:
        assert identity.check(*args, environment="staging")["environment"] == "staging"


# First install of the OAN release in an empty namespace: New Dev was the rehearsal.


@pytest.fixture
def first_install(oan_evidence):
    from oan_chart import profile
    pin = profile("staging")
    record = copy.deepcopy(oan_evidence)
    stamp = NOW.isoformat()
    for field in ("rehearsal", "cutover", "backups", "finalBackupAt"):
        del record[field]
    record.update(mode="first-install", firstInstall={
        "rehearsalEnvironment": "new-dev",
        "pin": {"chartVersion": pin["version"], "chartSha256": pin["sha256"], "platform": pin["platformVersion"],
                "valuesCommit": pin["values"]["commit"], "valuesSha256": pin["values"]["sha256"]},
        "newDev": {"release": "farmer-registry", "namespace": "farmer", "status": "deployed", "revision": 37,
                   "chartVersion": "1.0.0-dev.19", "platform": pin["platformVersion"], "allDeploymentsReady": True,
                   "observedAt": stamp},
        "stagingCommons": {"release": "commons-services", "namespace": "commons", "status": "deployed", "revision": 13,
                           "chartVersion": "1.0.0-dev.30", "gateway": "istio-system/staging", "observedAt": stamp},
        "target": {"namespace": "farmer", "releasePresent": False, "observedAt": stamp,
                   "databases": {"farmer_connector_v2": "absent", "farmer_registry": "absent", "farmer_registry_idgen": "absent"}}})
    return record


def verify_first(tmp_path, record, now=NOW, allow=True):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(record))
    return staging.evidence(path, SHA, now, allow_first_install=allow)


def test_first_install_evidence_needs_no_migration_flags_or_backup_inventory(tmp_path, first_install):
    record = verify_first(tmp_path, first_install)
    assert record["mode"] == "first-install" and record["registry"]["images"]["staff-api"]["digest"] == DIGEST


def test_first_install_evidence_is_refused_outside_the_fresh_install_action(tmp_path, first_install):
    with pytest.raises(ValueError, match="fresh-install"):
        verify_first(tmp_path, first_install, allow=False)
    with pytest.raises(ValueError):
        # cutover and upgrade call evidence() without the permission
        verify(tmp_path, first_install)


def test_first_install_evidence_is_refused_for_the_legacy_namespace(tmp_path, first_install):
    first_install.update(namespace="far", platform="1.2.2-rc.544")
    with pytest.raises(ValueError):
        verify_first(tmp_path, first_install)


@pytest.mark.parametrize("mutate", [
    lambda f: f["pin"].update(valuesSha256="0" * 64),
    lambda f: f["pin"].update(chartVersion="1.0.0-dev.19"),
    lambda f: f["pin"].update(valuesCommit="9" * 40),
    lambda f: f["newDev"].update(status="failed"),
    lambda f: f["newDev"].update(allDeploymentsReady=False),
    lambda f: f["newDev"].update(platform="1.2.2-rc.544"),
    lambda f: f["newDev"].update(namespace="far"),
    lambda f: f["newDev"].update(observedAt="2026-10-14T12:00:00+00:00"),
    lambda f: f["stagingCommons"].update(status="failed"),
    lambda f: f["stagingCommons"].update(gateway="far/internal"),
    lambda f: f["target"].update(releasePresent=True),
    lambda f: f["target"]["databases"].update(farmer_registry="present"),
    lambda f: f["target"]["databases"].pop("farmer_connector_v2"),
    lambda f: f["target"]["databases"].update(farmer_registry_far="absent"),
    lambda f: f["target"].update(observedAt="2026-10-14T12:00:00+00:00"),
])
def test_first_install_evidence_rejects_any_unproven_fact(tmp_path, first_install, mutate):
    mutate(first_install["firstInstall"])
    with pytest.raises(ValueError):
        verify_first(tmp_path, first_install)


def test_first_install_evidence_keeps_digests_freshness_and_rejects_a_backup_claim(tmp_path, first_install):
    with pytest.raises(ValueError):
        verify_first(tmp_path, first_install, NOW + timedelta(hours=25))
    first_install["backups"] = dict.fromkeys(("registry", "connector"), "2" * 64)
    with pytest.raises(ValueError, match="backup"):
        verify_first(tmp_path, first_install)
    del first_install["backups"]
    first_install["registry"]["images"]["celery"]["digest"] = "latest"
    with pytest.raises(ValueError):
        verify_first(tmp_path, first_install)


def test_first_install_does_not_relax_the_upgrade_shape(tmp_path, oan_evidence):
    del oan_evidence["backups"]
    with pytest.raises(ValueError, match="backup"):
        verify(tmp_path, oan_evidence)
    oan_evidence["backups"] = dict.fromkeys(("registry", "connector", "helm", "odkFormMedia", "pipelines", "runHistory", "checkpoints"), "2" * 64)
    oan_evidence["rehearsal"]["isolatedDatabases"] = False
    with pytest.raises(ValueError, match="verification"):
        verify(tmp_path, oan_evidence)
    oan_evidence["mode"] = "anything-else"
    with pytest.raises(ValueError, match="mode"):
        verify(tmp_path, oan_evidence)


def test_cli_mode_reports_first_install_only_for_fresh_install(tmp_path, first_install):
    path = tmp_path / "evidence.json"
    first_install.update(deliveryHash=module("staging_unpatched", "ci/deploy/staging.py").delivery_hash(), verifiedAt=datetime.now(timezone.utc).isoformat())
    for key in ("observedAt",):
        for block in ("newDev", "stagingCommons", "target"):
            first_install["firstInstall"][block][key] = first_install["verifiedAt"]
    path.write_text(json.dumps(first_install))
    base = dict(os.environ, DELIVERY_ENVIRONMENT="staging", STAGING_EVIDENCE_FILE=str(path), SOURCE_COMMIT=SHA)
    command = [sys.executable, str(ROOT / "ci/deploy/staging.py"), "mode"]
    ok = subprocess.run(command, env=dict(base, DELIVERY_ACTION="fresh-install"), capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.strip() == "first-install"
    for action in ("deploy", ""):
        refused = subprocess.run(command, env=dict(base, DELIVERY_ACTION=action), capture_output=True, text=True)
        assert refused.returncode == 1
