"""Offline repair proposals must preserve IDs and refuse an uncertain target."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("geo_repair", ROOT / "scripts/prepare-staging-geo-repair.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


@pytest.fixture
def catalog():
    levels, values = repair.audit.canonical_catalog()
    return {"levels": list(levels.values()), "values": list(values.values())}


def test_proposal_repairs_dangling_parent_without_guessing_farmer_reference(catalog):
    place = next(r for r in catalog["values"] if r["level_id"] == "level-kebele")
    place["parent_level_value_id"] = "a display name, not an ID"
    place["level_value_mnemonic"] = "Old 'name'"
    original = copy.deepcopy(catalog)
    refs = [{"table": "g2p_register_farmers", "geo_lowest_level_value_id": "legacy-unknown", "count": 7}]
    manifest, diff, unresolved, sql = repair.prepare(catalog, refs)
    assert manifest["catalogRowsChanged"] == 1
    assert manifest["parentChanges"] == manifest["labelChanges"] == 1
    assert manifest["applyAuthorized"] is False
    assert manifest["farmerReferenceUpdatesIncluded"] is False
    assert unresolved == refs and diff[0]["before"] == place
    assert catalog == original
    assert "Old ''name''" in sql
    assert "DELETE FROM" not in sql and "DROP TABLE public" not in sql
    assert "UPDATE public.g2p_geo_level_values" in sql
    assert "changed <> 1" in sql and "IS NOT DISTINCT FROM old" in sql
    assert "Catalog does not match the reviewed canonical target" in sql


@pytest.mark.parametrize("fault", ["missing-id", "extra-id", "wrong-level", "wrong-level-chain"])
def test_unsupported_catalog_changes_are_refused(catalog, fault):
    if fault == "missing-id":
        catalog["values"].pop()
    elif fault == "extra-id":
        row = dict(catalog["values"][0], level_value_id="unexpected")
        catalog["values"].append(row)
    elif fault == "wrong-level":
        catalog["values"][0]["level_id"] = "level-zone"
    else:
        catalog["levels"][0]["parent_level_id"] = "unexpected"
    with pytest.raises(ValueError):
        repair.prepare(catalog, [])


def test_canonical_rerun_is_an_exact_noop_proposal(catalog):
    manifest, diff, unresolved, sql = repair.prepare(catalog, [])
    assert manifest["catalogRowsChanged"] == 0
    assert not diff and not unresolved
    assert "THEN RETURN; END IF" in sql
