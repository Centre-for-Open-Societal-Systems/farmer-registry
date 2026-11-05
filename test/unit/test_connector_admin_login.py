"""The deployed connector image must carry the admin login beside the ODK attachment transfer."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ConnectorAdminLogin(unittest.TestCase):
    def test_the_overlay_uses_the_reviewed_login_module(self):
        reviewed = ROOT / "docker/registry-connector/src/openg2p_registry_connector_extension/admin_auth.py"
        overlay = ROOT / "integrations/registry-connector/oan_connector/admin_auth.py"
        self.assertEqual(reviewed.read_bytes(), overlay.read_bytes())

    def test_the_api_role_installs_the_login(self):
        entry = (ROOT / "integrations/registry-connector/oan_connector/__main__.py").read_text(encoding="utf-8")
        self.assertLess(entry.index("install_admin_auth(app)"), entry.index("runpy.run_module(\"openg2p_connector_service.main\""))


if __name__ == "__main__":
    unittest.main()
