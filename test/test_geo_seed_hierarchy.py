"""The Ethiopia location seed must be one connected tree.

The special woredas (Kebena, Mareko, Tembaro) were snapshotted with no parent.
Their zones then listed no woredas, so on Add Farmer -> Location the cascade
stopped at Zone and Village/Kebele stayed disabled. Nothing noticed, because a
row with a NULL parent is a valid row -- it is just unreachable from the UI.

Stdlib only; reads both copies of the seed (the db-seed JSON and the local-dev /
commons-services SQL dump) and checks every non-root location hangs off a
parent one level up that exists.
"""

import gzip
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEO_DIR = ROOT / "docker" / "db-seed" / "seed-data" / "geo"
SQL_GZ = ROOT / "docker" / "local-dev" / "geo-seed" / "ethiopia_geo_seed.sql.gz"
REPAIR_SQL = (ROOT / "farmer-extension" / "src" / "openg2p_registry_farmer_extension" / "meta_data"
              / "register-metadata" / "zz_farmer_special_woreda_names.sql")

VALUE_ROW = re.compile(
    r"INSERT INTO public\.g2p_geo_level_values \([^)]*\) VALUES "
    r"\('(?P<id>[^']*)', '(?P<level>[^']*)', '(?:[^']|'')*', (?P<parent>NULL|'[^']*'),"
)


def _json_rows():
    levels = json.loads((GEO_DIR / "geo_levels.json").read_text(encoding="utf-8"))
    values = json.loads((GEO_DIR / "geo_level_values.json").read_text(encoding="utf-8"))
    return levels, [(v["level_value_id"], v["level_id"], v.get("parent_level_value_id")) for v in values]


def _sql_rows():
    text = gzip.decompress(SQL_GZ.read_bytes()).decode("utf-8")
    rows = []
    for m in VALUE_ROW.finditer(text):
        parent = None if m.group("parent") == "NULL" else m.group("parent").strip("'")
        rows.append((m.group("id"), m.group("level"), parent))
    return rows


class GeoSeedHierarchy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        levels, cls.json_values = _json_rows()
        cls.parent_level = {lvl["level_id"]: lvl.get("parent_level_id") for lvl in levels}
        cls.sql_values = _sql_rows()

    def _assert_connected(self, rows, source):
        by_id = {vid: (level, parent) for vid, level, parent in rows}
        problems = []
        for vid, level, parent in rows:
            expected = self.parent_level.get(level)
            if expected is None:
                continue  # a root level (region)
            if parent is None:
                problems.append(f"{vid}: no parent")
            elif parent not in by_id:
                problems.append(f"{vid}: parent {parent} does not exist")
            elif by_id[parent][0] != expected:
                problems.append(f"{vid}: parent {parent} is a {by_id[parent][0]}, not a {expected}")
        self.assertEqual(problems, [], f"{source}: locations unreachable from the Location cascade")

    def test_json_seed_is_one_tree(self):
        self._assert_connected(self.json_values, "geo_level_values.json")

    def test_sql_seed_is_one_tree(self):
        self.assertGreater(len(self.sql_values), 20000, "SQL dump parsed to too few rows; regex drifted?")
        self._assert_connected(self.sql_values, SQL_GZ.name)

    def test_special_woredas_sit_under_their_special_zones(self):
        expected = {
            "woreda-ET070001": "zone-ET0705",  # Kebena SP woreda -> Kebena Special
            "woreda-ET072501": "zone-ET0706",  # Mareko SP woreda -> Mareko Special
            "woreda-ET072601": "zone-ET0707",  # Tembaro SP woreda -> Tembaro Special
        }
        for rows, source in ((self.json_values, "json"), (self.sql_values, "sql")):
            parents = {vid: parent for vid, _level, parent in rows}
            for woreda, zone in expected.items():
                with self.subTest(source=source, woreda=woreda):
                    self.assertEqual(parents.get(woreda), zone)

    def test_registry_name_repair_uses_the_seed_names(self):
        """zz_farmer_special_woreda_names.sql hardcodes woreda / zone / region
        names (the registry has no location tables to join); they must be the
        seed's, or the repair silently matches nothing."""
        sql = REPAIR_SQL.read_text(encoding="utf-8")
        triples = re.findall(r"\(''([^']+)'',\s*''([^']+)'',\s*''([^']+)''\)", sql)
        self.assertEqual(len(triples), 3, "expected one row per special woreda")
        values = json.loads((GEO_DIR / "geo_level_values.json").read_text(encoding="utf-8"))
        by_id = {v["level_value_id"]: v for v in values}
        expected = set()
        for woreda in ("woreda-ET070001", "woreda-ET072501", "woreda-ET072601"):
            zone = by_id[by_id[woreda]["parent_level_value_id"]]
            region = by_id[zone["parent_level_value_id"]]
            expected.add((by_id[woreda]["display_name"].lower(), zone["display_name"], region["display_name"]))
        self.assertEqual(set(triples), expected)

    def test_both_copies_agree(self):
        self.assertEqual(
            {vid: parent for vid, _l, parent in self.json_values},
            {vid: parent for vid, _l, parent in self.sql_values},
        )


if __name__ == "__main__":
    unittest.main()
