import re
import json
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[2]

class TestPhotoAndAttachmentStandards(unittest.TestCase):
    def test_sql_farmer_photo_metadata(self):
        sql_path = REPO / "farmer-extension/src/openg2p_registry_farmer_extension/meta_data/zz-oan/10_sections.sql"
        content = sql_path.read_text(encoding="utf-8")
        match = re.search(r"\x27(\{\"section-id\": \"farmer_photo\".*?\})\x27::jsonb", content, re.DOTALL)
        self.assertIsNotNone(match, "farmer_photo section JSON not found in 10_sections.sql")
        data = json.loads(match.group(1))
        widget = data["panels"][0]["widgets"][0]
        self.assertEqual(widget["widget-data-format"]["maxDimension"], 750)
        self.assertEqual(widget["widget-data-format"]["aspectRatio"], "4:5")
        self.assertEqual(widget["widget-data-validation"]["maxSizeKb"], 100)

    def test_sql_land_certificate_metadata(self):
        sql_path = REPO / "farmer-extension/src/openg2p_registry_farmer_extension/meta_data/zz-oan/10_sections.sql"
        content = sql_path.read_text(encoding="utf-8")
        match = re.search(r"\x27(\[\s*\{.*?\"widget\":\s*\"oan-file-cell\".*?\}\])\x27::jsonb", content, re.DOTALL)
        self.assertIsNotNone(match, "oan-file-cell columns JSON not found in 10_sections.sql")
        cols = json.loads(match.group(1))
        cert_col = next((c for c in cols if c.get("column-key") == "certificate_storage_id"), None)
        self.assertIsNotNone(cert_col)
        self.assertEqual(cert_col["widget-data-options"]["maxSize"], 2097152)

    def test_sql_form_documents_max_size(self):
        sql_path = REPO / "farmer-extension/src/openg2p_registry_farmer_extension/meta_data/zz-oan/12_form_sections.sql"
        content = sql_path.read_text(encoding="utf-8")
        self.assertIn("VALUES (5, '.pdf,.jpg,.jpeg,.png', 2097152)", content)

    def test_photo_widget_defaults(self):
        tsx_path = REPO / "ui/staff-ui/overrides/src/oan/widgets/FarmerPhotoWidget.tsx"
        content = tsx_path.read_text(encoding="utf-8")
        self.assertIn("maxDimension: 750", content)
        self.assertIn("maxSizeKb: 100", content)
        self.assertIn("targetRatio = 4 / 5", content)

if __name__ == "__main__":
    unittest.main()
