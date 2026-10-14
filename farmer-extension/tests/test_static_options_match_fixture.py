"""The static option lists in the register metadata must match the fixture.

scripts/sync-static-options.py inlines the farmer's reference lists
(lookup-data/g2p_attribute_values.sql) into every select that used to ask
Master Data for them, because Master Data never carried those lists (see the
script's docstring). Each generated source keeps its attribute_id, so this test
can re-derive it from the fixture and fail on drift in either direction: a
fixture row added or renamed without re-running the script, or an option
hand-edited in the SQL.

Stdlib only, deliberately: it must run on a developer host without the platform
package or a database, which is where the drift gets introduced.
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "sync-static-options.py"
META = ROOT / "farmer-extension" / "src" / "openg2p_registry_farmer_extension" / "meta_data" / "register-metadata"


def _load_script():
    spec = importlib.util.spec_from_file_location("sync_static_options", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = _load_script()


def _sources(node, acc):
    if isinstance(node, dict):
        source = node.get("widget-data-source")
        if isinstance(source, dict) and source.get("attribute_id"):
            acc.append((node.get("widget-id") or node.get("column-key"), source))
        for value in node.values():
            _sources(value, acc)
    elif isinstance(node, list):
        for value in node:
            _sources(value, acc)
    return acc


def _schemas():
    for path in sorted(META.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        for body in re.findall(r"\$schema\$(.*?)\$schema\$", text, re.DOTALL):
            yield path.name, json.loads(body.strip())
        for match in re.finditer(r"'(\{\"panels\".*?)'(?=\s*,)", text, re.DOTALL):
            yield path.name, json.loads(match.group(1).replace("''", "'"))


class TestStaticOptionsMatchFixture(unittest.TestCase):
    def test_generator_reports_no_drift(self):
        lists = sync.fixture_lists()
        for path in sorted(META.glob("*.sql")):
            text = path.read_text(encoding="utf-8")
            new, done = sync.rewrite(text, lists)
            self.assertEqual(new, text, f"{path.name}: run scripts/sync-static-options.py ({', '.join(sorted(set(done)))})")

    def test_every_attribute_select_is_static_and_matches_the_fixture(self):
        lists = sync.fixture_lists()
        seen = 0
        for filename, schema in _schemas():
            for widget_id, source in _sources(schema, []):
                with self.subTest(file=filename, widget=widget_id):
                    seen += 1
                    self.assertEqual(source.get("type"), "static")
                    expected = [{"label": d, "value": c} for c, d in lists[source["attribute_id"]]]
                    self.assertEqual(source.get("options"), expected)
        self.assertGreater(seen, 0)

    def test_no_select_still_asks_master_data_for_a_farmer_list(self):
        for filename, schema in _schemas():
            text = json.dumps(schema)
            self.assertNotIn('"service": "attributes"', text, f"{filename}: attributes lookup left in place")
