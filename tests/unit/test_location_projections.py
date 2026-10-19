import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


repair = module("location_repair", "scripts/operations/staging/repair_location_projections.py")
geo = module("canonical_geo_repair", "scripts/check-odk-geo-compatibility.py")


def test_fingerprint_matches_canonical_seed_and_preserves_hierarchy():
    levels, values = geo.canonical_catalog()
    catalog = {"levels": list(levels.values()), "values": list(values.values())}
    assert repair.catalog_digest(catalog) == repair.CANONICAL_SHA256
    leaf = next(k for k, v in values.items() if v["level_id"] == "level-kebele")
    chain = repair.hierarchy_for(values, leaf)
    assert [n["level_mnemonic"] for n in chain] == ["region", "zone", "woreda", "kebele"]
    assert chain[-1]["level_value_id"] == leaf
    assert set(repair.projections(chain)) == {"region_name", "zone_name", "woreda_name", "kebele_name", "woreda_level_value_id", "geo_code_hierarchy_json"}


@pytest.mark.parametrize("database,rehearsal,allowed", [("farmer_registry_far", False, True), ("farmer_registry", False, False), ("master_data", False, False), ("farmer_seed_rehearsal_test", True, True), ("farmer_registry_far", True, False)])
def test_database_scope(database, rehearsal, allowed):
    class Cursor:
        def execute(self, query):
            assert query == "SELECT current_database()"

        def fetchone(self):
            return (database,)
    if allowed:
        repair.check_database(Cursor(), rehearsal)
    else:
        with pytest.raises(ValueError, match="outside"):
            repair.check_database(Cursor(), rehearsal)
