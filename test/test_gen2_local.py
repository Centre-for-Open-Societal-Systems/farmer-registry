"""Offline cutover contracts; these do not establish live API compatibility."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import unittest
import uuid
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gen2_local_render", ROOT / "local/gen2/render.py")
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class LocalTopology(unittest.TestCase):
    def setUp(self):
        cache = ROOT / ".cache"
        cache.mkdir(exist_ok=True)
        # Inherit workspace ACLs on Windows; tempfile's owner-only directory
        # ACL can exclude a managed runner's restricted token.
        self.output = cache / ("gen2-test-" + uuid.uuid4().hex)
        self.output.mkdir()
        assert self.output.resolve().is_relative_to(cache.resolve())
        self.addCleanup(shutil.rmtree, self.output)
        self.shared, self.farmer = renderer.render(self.output)

    def test_farmer_owns_no_shared_services_or_placeholder_containers(self):
        self.assertFalse(set(renderer.SHARED).intersection(self.farmer["services"]))
        for service in self.farmer["services"].values():
            self.assertNotIn("busybox", service.get("image", ""))
            self.assertTrue(set(service.get("depends_on", {})) <= self.farmer["services"].keys())

    def test_common_dependencies_are_internal_to_the_shared_project(self):
        for service in self.shared["services"].values():
            self.assertTrue(set(service.get("depends_on", {})) <= self.shared["services"].keys())

    def test_database_and_object_volumes_are_existing_external_volumes(self):
        self.assertEqual(self.shared["volumes"]["postgres-data"],
                         {"external": True, "name": "openg2p-shared_postgres-data"})
        self.assertEqual(self.shared["volumes"]["minio-data"],
                         {"external": True, "name": "farmer-registry_minio-data"})
        self.assertFalse(any("initdb" in m for m in self.shared["services"]["postgres"]["volumes"]))
        self.assertNotIn("--import-realm", self.shared["services"]["keycloak"]["command"])

    def test_no_data_or_identity_jobs_run_in_default_startup(self):
        for doc, name in ((self.shared, "master-data-seed"), (self.shared, "keycloak-init"),
                          (self.shared, "register-apps"), (self.shared, "minio-init"),
                          (self.farmer, "farmer-registry-db-seed"), (self.farmer, "reporting-views")):
            self.assertTrue(doc["services"][name]["profiles"])
        seed = self.farmer["services"]["farmer-registry-db-seed"]["environment"]
        for key in ("LOAD_GEO_DATA", "LOAD_SAMPLE_DATA", "LOAD_IMAGES"):
            self.assertEqual(seed[key], "false")
        self.assertNotIn("farmer-registry-geo-remap", self.farmer["services"])

    def test_session_cache_matches_iam_but_queue_lifecycle_is_separate(self):
        iam = self.shared["services"]["iam-staff-api"]["environment"]["IAM_STAFF_AUTH_REDIS_URL"]
        staff = self.farmer["services"]["farmer-registry-staff-api"]["environment"]
        self.assertEqual(iam, staff["REGISTRY_STAFF_PORTAL_API_AUTH_REDIS_URL"])
        for name in ("farmer-registry-celery-worker", "farmer-registry-celery-beat"):
            for key, value in self.farmer["services"][name]["environment"].items():
                if "CELERY_BROKER_URL" in key or "CELERY_BACKEND_URL" in key:
                    self.assertEqual(value, "redis://queue:6379/0")

    def test_shared_awe_can_resolve_the_registry_callback(self):
        self.assertEqual(self.shared["networks"], self.farmer["networks"])
        self.assertTrue(self.shared["networks"]["default"]["external"])
        for name in ("farmer-registry-staff-api", "farmer-registry-celery-worker"):
            urls = [v for k, v in self.farmer["services"][name]["environment"].items() if k.endswith("AWE_DEFAULT_CALLBACK_URL")]
            self.assertEqual(urls, ["http://farmer-registry-staff-api:8000/awe/webhooks/decision"])

    def test_browser_issuer_cookie_and_presigned_url_contracts(self):
        provider = json.loads((self.output / "iam-login-providers.json").read_text())[0]
        self.assertEqual(provider["issuer"], renderer.ISSUER)
        self.assertEqual(provider["oauth_callback_url"], renderer.IAM + "/auth/callback")
        self.assertEqual(provider["default_redirect_uri"], renderer.HUB + "/")
        ui = json.loads((self.output / "awe-ui-config.json").read_text())
        self.assertEqual(ui["keycloak"]["realm"], "farmer")
        for name in ("farmer-registry-staff-api", "farmer-registry-partner-api"):
            env = self.farmer["services"][name]["environment"]
            self.assertEqual([v for k, v in env.items() if k.endswith("MINIO_ENDPOINT")], [renderer.MINIO])
        init = (self.output / "keycloak-init.sh").read_text()
        self.assertNotRegex(init, r"http://localhost:")

    def test_partner_security_and_consent_audiences_match_chart_contract(self):
        env = self.farmer["services"]["farmer-registry-partner-api"]["environment"]
        self.assertEqual(env["REGISTRY_PARTNER_API_SIGNATURE_VALIDATION_ENABLED"], "true")
        self.assertEqual(env["REGISTRY_PARTNER_API_CONSENT_ENFORCEMENT_ENABLED"], "true")
        self.assertEqual(env["REGISTRY_PARTNER_API_CONSENT_MANAGER_URL"], "http://cm-partner-api:8000")
        staff = self.shared["services"]["consent-manager-api"]["environment"]
        partner = self.shared["services"]["cm-partner-api"]["environment"]
        self.assertEqual(staff["CONSENT_MANAGER_AUTH_ENABLED"], "true")
        self.assertEqual(partner["CONSENT_MANAGER_API_AUDIENCE"], "partner")
        self.assertEqual(staff["CONSENT_MANAGER_CM_SIGNING_P12_PATH"], partner["CONSENT_MANAGER_CM_SIGNING_P12_PATH"])

    def test_only_this_worktree_is_built_and_old_images_are_preserved(self):
        for service in self.farmer["services"].values():
            if "build" in service:
                self.assertEqual(service["build"]["context"], ROOT.as_posix())
                self.assertIn("farmer-gen2-local/", service["image"])
        gate = self.farmer["services"]["preflight"]
        self.assertEqual(gate["entrypoint"], ["python", "/checks/preflight.py"])
        self.assertNotIn("depends_on", gate)

    def test_reporting_job_only_executes_scripts_shipped_by_farmer(self):
        service = self.farmer["services"]["reporting-views"]
        self.assertIn("sh /seed/reporting_geo_levels.sh", service["entrypoint"][-1])
        self.assertNotIn("generate_reporting_views.py", service["entrypoint"][-1])
        self.assertEqual(self.farmer["services"]["registry-dashboard-api"]["ports"], ["127.0.0.1:8105:8000"])

    def test_published_chart_image_pins(self):
        chart = ROOT / ".cache/gen2-charts/openg2p-commons-services-2.3.4-rc.245.tgz"
        if not chart.exists():
            self.skipTest("download the published Commons chart to verify image provenance")
        mapping = {"iam-staff-api": ("openg2p-iam-service", "iamStaffPortalApi"),
                   "farmer-master-data-api": ("openg2p-master-data", "masterDataAPI"),
                   "awe": ("openg2p-awe", "awe"), "awe-ui": ("openg2p-awe", "ui"),
                   "pm-staff-api": ("partner-management", "staffPortalApi"),
                   "pm-partner-api": ("partner-management", "partnerApi"),
                   "consent-manager-api": ("openg2p-consent-manager", "consentManagerApi"),
                   "audit-manager": ("openg2p-audit-manager", "auditManager"),
                   "staff-portal": ("openg2p-staff-portal-ui", "staffPortalUi")}
        with tarfile.open(chart) as archive:
            for service, (subchart, component) in mapping.items():
                values = yaml.safe_load(archive.extractfile(f"openg2p-commons-services/charts/{subchart}/values.yaml"))
                image = values[component]["image"]
                self.assertEqual(self.shared["services"][service]["image"], image["repository"] + ":" + image["tag"])

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI is required; engine is not")
    def test_real_compose_parser_accepts_all_profiles(self):
        for name in ("shared", "farmer"):
            result = subprocess.run(["docker", "compose", "-f", str(self.output / (name + ".compose.json")),
                                     "--profile", "*", "config", "--quiet"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


class StartupFailure(unittest.TestCase):
    def test_queue_cutover_rejects_pending_or_unreadable_queue(self):
        sys.path.insert(0, str(ROOT / "local/gen2"))
        self.addCleanup(sys.path.pop, 0)
        import stack
        for reply in ("3", "NOAUTH Authentication required"):
            with self.subTest(reply=reply), patch.object(stack, "running", return_value=set()), \
                 patch.object(stack, "run", return_value=reply):
                with self.assertRaisesRegex(RuntimeError, "not empty"):
                    stack.require_queue_cutover()

    def test_failed_preflight_prevents_farmer_up(self):
        sys.path.insert(0, str(ROOT / "local/gen2"))
        self.addCleanup(sys.path.pop, 0)
        import stack
        with patch.object(stack, "render", return_value=({}, {})), patch.object(stack, "run"), \
             patch.object(stack, "compose", side_effect=subprocess.CalledProcessError(1, "preflight")) as compose, \
             patch.object(sys, "argv", ["stack.py", "farmer-up"]):
            with self.assertRaises(subprocess.CalledProcessError):
                stack.main()
        compose.assert_called_once_with("farmer", "run", "--rm", "--no-deps", "preflight")


if __name__ == "__main__":
    unittest.main()
