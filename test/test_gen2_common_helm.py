"""Render the real pinned registry chart: no mocks, cluster or credentials.

Requires helm + PyYAML. Run `helm dependency update helm/openg2p-farmer-registry`
first. CI installs both tools; local runs without Helm skip the render tests.
"""

import copy
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
CHART = REPO / "helm" / "openg2p-farmer-registry"
DEV = CHART / "environments" / "dev-common.yaml"
SPEC = importlib.util.spec_from_file_location("gen2_validator", REPO / "ci/gen2/validate_manifest.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


@pytest.fixture(scope="module")
def helm():
    executable = os.environ.get("HELM_BIN") or shutil.which("helm")
    if not executable:
        pytest.skip("install helm or set HELM_BIN to run real chart rendering")
    return executable


def render(helm, *files, release="farmer-registry", namespace="far", extra=()):
    args = [helm, "template", release, str(CHART), "-n", namespace]
    for file in files:
        args += ["-f", str(file)]
    result = subprocess.run(args + list(extra), capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    return validator.documents(result.stdout)


@pytest.fixture(scope="module")
def rendered(helm, tmp_path_factory):
    path = tmp_path_factory.mktemp("gen2") / "browser.yaml"
    browser = yaml.safe_load((REPO / "ci/gen2/browser-values.example.yaml").read_text())
    # Fictional test URLs only. No production hostname is assumed by the profile.
    text = yaml.safe_dump(browser).replace("dev.example.org", "dev.test.openg2p.invalid")
    path.write_text(text, encoding="utf-8")
    return render(helm, DEV, path)


def resource(docs, kind, name):
    return next(d for d in docs if d.get("kind") == kind and d["metadata"]["name"] == name)


def change_env(docs, suffix, key, value):
    doc = resource(docs, "Deployment", "farmer-registry-" + suffix)
    container = validator.pod_spec(doc)["containers"][0]
    entry = next(e for e in container["env"] if e["name"] == key)
    entry["value"] = value


def test_gen2_render_matches_contract(rendered):
    assert validator.validate(rendered) == []


def test_base_and_services_share_the_exact_rc_pin():
    defaults = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    dev = yaml.safe_load(DEV.read_text(encoding="utf-8"))
    assert defaults["sharedCommons"] == dev["sharedCommons"] | {"enabled": False}
    assert dev["sharedCommons"]["chartVersion"] == "2.3.4-rc.245"
    assert dev["sharedCommons"]["namespace"] == "common"


def test_shared_contract_matches_both_published_commons_artifacts():
    """CI downloads both RCs. Local runs can supply the same Helm pull cache."""
    version = yaml.safe_load(DEV.read_text(encoding="utf-8"))["sharedCommons"]["chartVersion"]
    cache = Path(os.environ.get("COMMONS_CHART_CACHE", REPO / ".cache/gen2-charts"))
    values = {}
    for name in ("openg2p-commons-base", "openg2p-commons-services"):
        path = cache / f"{name}-{version}.tgz"
        if not path.exists():
            if os.environ.get("CI"):
                pytest.fail(f"CI must download {path} before the contract checks")
            pytest.skip(f"helm pull {name} --version {version} into {cache}")
        with tarfile.open(path) as tar:
            chart = yaml.safe_load(tar.extractfile(f"{name}/Chart.yaml"))
            values[name] = yaml.safe_load(tar.extractfile(f"{name}/values.yaml"))
            assert chart["name"] == name and chart["version"] == version
            dependencies = {d.get("alias", d["name"]): d for d in chart["dependencies"]}
            assert not any("novu" in key for key in dependencies)
            if name.endswith("services"):
                assert dependencies["master-data"]["version"] == "1.1.4-rc.104"
                assert dependencies["openg2p-iam-service"]["version"] == "1.4.4-rc.125"
                assert dependencies["openg2p-awe"]["version"] == "1.2.2"
                master_data = values[name]["master-data"]
                assert "masterDataApi" in master_data and "masterDataAPI" not in master_data
                assert master_data["global"]["masterDataDBSecret"] == "master-data-db-user"
                assert master_data["global"]["masterDataDBUserPasswordKey"] == "master-data-db-user-password"
    assert values["openg2p-commons-base"]["global"]["redisInstallationName"] == '{{ .Release.Name }}-redis'
    assert values["openg2p-commons-services"]["global"]["redisInstallationName"] == "commons-redis"


def test_existing_geography_and_records_are_not_reseeded(rendered):
    seed = resource(rendered, "Job", "farmer-registry-db-seed")
    env = list(validator.environments(seed))[-1][1]
    assert all(env[k] == "false" for k in ("LOAD_GEO_DATA", "LOAD_SAMPLE_DATA", "LOAD_IMAGES"))
    assert env["LOAD_TEMPLATES"] == "true"
    assert not any("bulk-sample" in d.get("metadata", {}).get("name", "") for d in rendered)


def test_namespace_local_master_data_secret_names_match_latest_commons(rendered):
    for name, variable in [("farmer-registry-db-seed", "MD_PGPASSWORD"),
                           ("farmer-registry-fr-reporting-views", "MDS_PGPASSWORD")]:
        pod = validator.pod_spec(resource(rendered, "Job", name))
        entry = next(e for e in pod["containers"][0]["env"] if e["name"] == variable)
        assert entry["valueFrom"]["secretKeyRef"] == {
            "name": "master-data-db-user", "key": "master-data-db-user-password",
        }


def test_alias_only_exists_for_the_opt_in_dev_profile(helm):
    for files in ((), (CHART / "environments/staging-legacy.yaml",)):
        docs = render(helm, *files)
        assert not any(d.get("kind") == "Service" and d["metadata"]["name"] == "commons-services-awe" for d in docs)


def test_callback_follows_the_actual_release_namespace(helm):
    docs = render(helm, DEV, release="farmer-two", namespace="far-two")
    env = list(validator.environments(resource(docs, "Job", "farmer-two-db-seed")))[-1][1]
    assert env["AWE_CALLBACK_CALLER_SERVICE"] == "http://farmer-two-staff-portal-api.far-two.svc.cluster.local/awe/webhooks/decision"


def test_same_namespace_alias_is_rejected(helm):
    result = subprocess.run([helm, "template", "farmer-registry", str(CHART), "-n", "common", "-f", str(DEV)],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode != 0
    assert "sharedCommons.namespace must differ" in result.stderr


def test_live_short_names_cannot_override_the_tracked_common_wiring(helm, tmp_path):
    live = tmp_path / "live.yaml"
    live.write_text(yaml.safe_dump({
        "global": {"postgresqlHost": "commons-postgresql", "masterDataApiUrl": "http://old-master-data"},
        "registry": {"staffApi": {"envVars": {"REGISTRY_STAFF_PORTAL_API_AUTH_REDIS_URL": "redis://old-redis:6379/0"}}},
    }), encoding="utf-8")
    docs = render(helm, live, DEV)
    staff = resource(docs, "Deployment", "farmer-registry-staff-portal-api")
    env = list(validator.environments(staff))[-1][1]
    assert env["REGISTRY_STAFF_PORTAL_API_DB_HOSTNAME"].endswith(".common.svc.cluster.local")
    assert env["REGISTRY_STAFF_PORTAL_API_AUTH_REDIS_URL"] == "redis://commons-redis-master.common.svc.cluster.local:6379/0"


@pytest.mark.parametrize("suffix,key,value", [
    ("staff-portal-api", "REGISTRY_STAFF_PORTAL_API_AUTH_REDIS_URL", "redis://commons-redis-master:6379/0"),
    ("staff-portal-api", "REGISTRY_STAFF_PORTAL_API_CSRF_ENABLED", "false"),
    ("partner-api", "REGISTRY_PARTNER_API_SIGNATURE_VALIDATION_ENABLED", "false"),
    ("partner-api", "REGISTRY_PARTNER_API_CONSENT_ENFORCEMENT_ENABLED", "false"),
    ("celery-worker", "REGISTRY_CELERY_WORKERS_AWE_DEFAULT_CALLBACK_URL", "http://farmer-registry-staff-portal-api/awe/webhooks/decision"),
    ("staff-portal-ui", "IAM_URL", "http://commons-services-iam-staff-portal-api.common.svc.cluster.local"),
    ("staff-portal-ui", "COOKIE_DOMAIN", ".wrong.invalid"),
    ("staff-portal-ui", "KEYCLOAK_LOGOUT_URL", "http://commons-keycloak.common.svc.cluster.local/realms/staff/protocol/openid-connect/logout"),
    ("staff-portal-ui", "APPLICATION_MNEMONIC", "another-registry-staff-portal"),
])
def test_validator_rejects_broken_common_and_browser_wiring(rendered, suffix, key, value):
    docs = copy.deepcopy(rendered)
    change_env(docs, suffix, key, value)
    assert validator.validate(docs)


def test_placeholder_browser_values_are_rejected(helm):
    docs = render(helm, DEV, REPO / "ci/gen2/browser-values.example.yaml")
    assert any("example/default hostname" in e for e in validator.validate(docs))


def test_public_ui_preserves_its_origin_and_ca_but_uses_common(helm, tmp_path):
    live = tmp_path / "live.yaml"
    live.write_text(yaml.safe_dump({
        "global": {
            "registryHostname": "farmer.dev.test.openg2p.invalid",
            "keycloakBaseUrl": "https://keycloak.dev.test.openg2p.invalid",
            "minioHost": "minio.dev.test.openg2p.invalid",
            "minioSecure": True,
        },
        "registry": {"staffUi": {"envVars": {
            "IAM_URL": "https://staff-iam.dev.test.openg2p.invalid",
            "COOKIE_DOMAIN": ".dev.test.openg2p.invalid",
        }}},
        "publicStaffUi": {
            "enabled": True,
            "env": {
                "APP_URL": "https://public-farmer.dev.test.openg2p.invalid",
                "IAM_URL": "https://staff-iam.dev.test.openg2p.invalid",
                "COOKIE_DOMAIN": ".dev.test.openg2p.invalid",
                "MASTERDATA_BACKEND_API_URL": "http://old-master-data",
            },
            "volumes": [{"name": "ca", "configMap": {"name": "far-ca-bundle"}}],
            "volumeMounts": [{"name": "ca", "mountPath": "/etc/ssl/local-ca", "readOnly": True}],
        },
    }), encoding="utf-8")
    docs = render(helm, live, DEV)
    public = resource(docs, "Deployment", "farmer-registry-staff-portal-ui-public")
    env = list(validator.environments(public))[-1][1]
    assert env["APP_URL"] == "https://public-farmer.dev.test.openg2p.invalid"
    assert env["MASTERDATA_BACKEND_API_URL"].endswith(".common.svc.cluster.local")
    assert validator.pod_spec(public)["volumes"][0]["configMap"]["name"] == "far-ca-bundle"
    assert validator.validate(docs) == []
    change_env(docs, "staff-portal-ui-public", "COOKIE_DOMAIN", ".wrong.invalid")
    assert any("public staff UI COOKIE_DOMAIN" in e for e in validator.validate(docs))


@pytest.mark.parametrize("mode,ok", [("absent", True), ("owned", True),
                                      ("unowned", False), ("wrong-target", False),
                                      ("missing-key", False), ("forbidden", False)])
def test_namespace_preflight_is_read_only_and_fail_closed(tmp_path, mode, ok):
    bash = os.environ.get("BASH_BIN") or shutil.which("bash")
    if not bash:
        pytest.skip("bash is needed to exercise the preflight script")
    mock = tmp_path / "kubectl"
    mock.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$KUBE_LOG"
[ "$MODE" != forbidden ] || exit 1
if [ "$1 $2" = 'get secret' ]; then
  [ "$MODE" != missing-key ] || [ "$3" != commons-keycloak ] || exit 0
  printf present
elif [ "$1 $2" = 'get service' ]; then
  case "$MODE" in
    owned) printf 'commons-services-awe.common.svc.cluster.local|farmer-registry|far|Helm';;
    unowned) printf 'commons-services-awe.common.svc.cluster.local|<no value>|<no value>|<no value>';;
    wrong-target) printf 'commons-services-awe.commons.svc.cluster.local|farmer-registry|far|Helm';;
  esac
else
  exit 64
fi
''', encoding="utf-8")
    mock.chmod(0o755)
    log = tmp_path / "requests.log"
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
               KUBE_LOG=log.as_posix(), MODE=mode, HELM_NAMESPACE="far", HELM_RELEASE="farmer-registry")
    result = subprocess.run([bash, (REPO / "ci/gen2/preflight.sh").as_posix()], env=env,
                            capture_output=True, text=True, encoding="utf-8")
    assert (result.returncode == 0) == ok, result.stderr
    requests = log.read_text()
    assert all(line.startswith("get ") and " -n far " in line for line in requests.splitlines())
    assert " -o json" not in requests and " -o yaml" not in requests
    if ok:
        assert "commons-services-staff-portal" in requests


def test_jenkins_renders_and_upgrades_with_the_same_values():
    text = (REPO / "Jenkinsfile").read_text()
    assert "? 'dev-common' : 'staging-legacy'" in text
    assert text.count('"\\$@" > /tmp/far-new-') == 1
    assert text.count('"\\$@" --timeout 20m') == 1
    assert "ci/gen2/preflight.sh" in text
    assert "loadAttributes:" not in text


def test_legacy_api_builds_use_the_shared_patcher():
    for component in ("staff-api", "partner-api", "celery"):
        text = (REPO / "docker" / component / "Dockerfile").read_text()
        assert "COPY docker/patches/patch_platform.py" in text
        assert "async def _build_intake_policy_condition" not in text
