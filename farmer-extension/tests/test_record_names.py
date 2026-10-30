"""Tests for the readable record names (register_domain/record_names.py).

The module has no framework imports, so it is loaded as a stand-in package and
these tests run without the registry installed.
"""

import importlib
import sys
import types
from pathlib import Path

_package = types.ModuleType("oan_register_domain")
_package.__path__ = [str(Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension/register_domain")]
sys.modules.setdefault("oan_register_domain", _package)
names = importlib.import_module("oan_register_domain.record_names")
compose = names.compose


def test_farmer_name_has_first_father_and_grandfather():
    assert compose("Farmer", {"first_name": "Berhanu", "middle_name": "Abebe", "last_name": "Assefa"}) == "Berhanu Abebe Assefa"


def test_farmer_name_skips_empty_parts_and_collapses_spaces():
    assert compose("Farmer", {"first_name": " Berhanu ", "middle_name": None, "last_name": "Assefa"}) == "Berhanu Assefa"
    assert compose("Farmer", {"first_name": "Abebe", "middle_name": "", "last_name": "  "}) == "Abebe"
    assert compose("Farmer", {"first_name": "Mary  Ann", "middle_name": "Lee", "last_name": None}) == "Mary Ann Lee"


def test_farmer_without_any_name_composes_nothing():
    assert compose("Farmer", {"first_name": None}) == ""


def test_land_name_from_size_unit_and_use():
    assert compose("Land", {"land_size": "1.250000", "unit": "HECTARE", "current_land_use": "GRAZING"}) == "1.25 Hectare, Grazing"
    assert compose("Land", {"land_size": 2, "unit": "SQUARE_METER", "current_land_use": None}) == "2 Square Meter"
    assert compose("Land", {"land_size": 10, "unit": "HECTARE"}) == "10 Hectare"
    assert compose("Land", {"land_size": "abc", "unit": "HECTARE"}) == "abc Hectare"
    assert compose("Land", {}) == ""


def test_crop_name_drops_code_prefixes():
    assert compose("Crop", {"commodity": "CROP_TEFF", "season": "SEASON_MEHER"}) == "Teff, Meher"
    assert compose("Crop", {"commodity": "CROP_FABA_BEAN", "season": None}) == "Faba Bean"


def test_livestock_name_has_breed_in_brackets():
    assert compose("Livestock", {"livestock_type": "LSTK_CATTLE", "breed": "BREED_LOCAL"}) == "Cattle (Local)"
    assert compose("Livestock", {"livestock_type": "LSTK_CHICKEN"}) == "Chicken"


def test_text_that_is_not_a_code_is_kept_as_typed():
    assert compose("Crop", {"commodity": "Teff for testing", "season": "Meher"}) == "Teff for testing, Meher"


def test_phone_name_is_type_and_number():
    assert compose("FarmerPhone", {"phone_type": "PRIMARY", "phone_number": "941923320"}) == "Primary 941923320"
    assert compose("FarmerPhone", {"phone_type": None, "phone_number": "941923320"}) == "941923320"


def test_membership_name_prefers_primary_then_union_then_cluster():
    both = {"primary_cooperative_name": "Tsehay Primary Cooperative", "cooperative_union_name": "Raya Farmers Cooperative Union"}
    assert compose("MembershipDetails", both) == "Tsehay Primary Cooperative"
    assert compose("MembershipDetails", {"cooperative_union_name": "Raya Farmers Cooperative Union"}) == "Raya Farmers Cooperative Union"
    assert compose("MembershipDetails", {"farmer_cluster_role": "CHAIRPERSON"}) == "Farmer cluster, Chairperson"
    assert compose("MembershipDetails", {}) == ""


def test_farm_inputs_name_lists_what_was_used():
    row = {"fertilizer_use": True, "pesticide_use": False, "improved_seed_use": True, "water_source": "RAINFED"}
    assert compose("FarmInputs", row) == "Farm inputs (fertilizer, improved seed, water: Rainfed)"
    assert compose("FarmInputs", {"fertilizer_use": False}) == ""


def test_unknown_register_composes_nothing():
    assert compose("Household", {"first_name": "A"}) == ""
