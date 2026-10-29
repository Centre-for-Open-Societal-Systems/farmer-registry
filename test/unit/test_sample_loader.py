"""The db-seed sample loader: Master Data's sample people plus the pack's farm facts, as approved sample records."""

import ast
import hashlib
import importlib.util
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "docker/db-seed"


@pytest.fixture(scope="module")
def loader():
    stubs = {"psycopg2": types.ModuleType("psycopg2"), "psycopg2.extras": types.ModuleType("psycopg2.extras")}
    stubs["psycopg2.extras"].Json = lambda value: ("json", value)
    stubs["psycopg2"].extras = stubs["psycopg2.extras"]
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("farmer_sample_loader", SEED / "load_sample_data.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_loader_signs_in_as_nobody_and_approves_nothing():
    source = (SEED / "load_sample_data.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    # Master Data through the platform's client is its only network access.
    assert not imported & {"urllib", "requests", "httpx", "http", "socket", "keycloak"}
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    for forbidden in ("grant_type", "KEYCLOAK", "INTAKE_SEED", "STAFF_", "/intake-form-data",
                      "approve_", "/approve", "finalize", "awe_", "AWE_"):
        assert forbidden not in code, forbidden
    client = (SEED / "mds_client.py").read_text(encoding="utf-8")
    assert client.count('"grant_type"') == 1 and '"grant_type": "client_credentials"' in client
    assert "password" not in client.lower()


def test_master_data_client_is_the_platforms_unchanged():
    digest = hashlib.sha256((SEED / "mds_client.py").read_bytes()).hexdigest()
    assert digest == "2ca03a9c4f40cceb91ad839b272335f47eabee3982685bdd20639dce6bc36c5b"
    dockerfile = (SEED / "Dockerfile").read_text(encoding="utf-8")
    assert "registry-platform docker/db-seed/mds_client.py at e7e6e269" in dockerfile
    assert "ARG OPENG2P_DATA_REPO=https://github.com/Centre-for-Open-Societal-Systems/openg2p-data.git" in dockerfile
    assert "ARG OPENG2P_DATA_REF=dc7e7bf69087b4684a3608fdd4bf98100aab77a8" in dockerfile


CHAIN = [
    {"unit_id": "ET", "name": "Ethiopia", "level_id": "l0", "level_mnemonic": "country"},
    {"unit_id": "ET01", "name": "Tigray", "level_id": "l1", "level_mnemonic": "region"},
    {"unit_id": "ET0101", "name": "North Western", "level_id": "l2", "level_mnemonic": "zone"},
    {"unit_id": "ET010101", "name": "Tahtay Adiyabo", "level_id": "l3", "level_mnemonic": "woreda"},
    {"unit_id": "ET01010102", "name": "Badme", "level_id": "l4", "level_mnemonic": "kebele"},
]


def person(n, household, relationship, nid, gender="MALE", born="1984-08-06", **more):
    return {"individual_id": f"ETH-IND-{n:04d}", "household_id": household, "given_name": f"Given{n}",
            "fathers_name": f"Father{n}", "gender": gender, "relationship_to_head": relationship,
            "marital_status": "MARRIED", "education_level": "PRIMARY", "disability_status": "NO",
            "birth_date": born, "phone": "+251941923320", "national_id": nid, "geo_pcode": "ET01010102",
            "address_parts": {"house_number": "1145"}, "latitude": 14.4, "longitude": 37.7, "country": "ETH",
            **more}


PEOPLE = [person(1, "ETH-HH-001", "SELF", "502628318720"),
          person(2, "ETH-HH-001", "CHILD", "721996394985", gender="FEMALE", born="2015-01-01"),
          person(3, "ETH-HH-002", "SELF", "514082761996")]
HOUSEHOLDS = [{"household_id": "ETH-HH-001", "head_individual_id": "ETH-IND-0001", "geo_pcode": "ET01010102",
               "country": "ETH", "address_parts": {"house_number": "1145"}},
              {"household_id": "ETH-HH-002", "head_individual_id": "ETH-IND-0003", "geo_pcode": "ET01010102",
               "country": "ETH"}]
FARMS = {"ETH-IND-0001": {
    "individual_id": "ETH-IND-0001",
    "farmer": {"grandfathers_name": "Assefa", "language_spoken": "TIGRINYA", "identity_document_type": "FAYDA",
               "income_sources": ["SOI_CROP_PRODUCTION"], "phone_type": "PRIMARY"},
    "lands": [{"land_ref": "L1", "land_size": 0.5, "unit": "HECTARE", "current_land_use": "AGRICULTURAL"},
              {"land_ref": "L2", "land_size": 1.25, "unit": "HECTARE", "current_land_use": "GRAZING"}],
    "crops": [{"land_ref": "L1", "commodity": "CROP_TEFF", "season": "SEASON_MEHER", "water_sources": ["WS_RAINFED"]}],
    "livestock": [{"land_ref": "L2", "livestock_type": "LSTK_CATTLE", "breed": "BREED_LOCAL", "head_count": 4}],
    "farm_inputs": [{"land_ref": "L1", "fertilizer_use": True}],
    "membership": {"is_primary_cooperative_member": True, "primary_cooperative_name": "Tsehay Primary Cooperative"},
}}
NOW = datetime(2026, 10, 29, 12, 0)


def plan(loader, registered=frozenset(), member_households=None):
    return loader.plan(PEOPLE, HOUSEHOLDS, FARMS, loader.Geography(lambda pcode: CHAIN), set(registered),
                       member_households or {}, NOW)


def test_people_become_numbered_farmers_in_their_households_with_their_farms(loader):
    rows = plan(loader)
    households = {r["functional_record_id"]: r for r in rows["g2p_register_households"]}
    assert sorted(households) == ["HH-0001", "HH-0002"]
    first = households["HH-0001"]
    assert (first["household_head"], first["size_of_group"], first["number_of_children"]) == \
        ("Given1 Father1 Assefa", 2, 1)
    farmers = {r["functional_record_id"]: r for r in rows["g2p_register_farmers"]}
    assert sorted(farmers) == ["FR-0001", "FR-0002", "FR-0003"]
    head = farmers["FR-0001"]
    assert head["link_internal_record_id"] == first["internal_record_id"]
    assert (head["first_name"], head["middle_name"], head["last_name"]) == ("Given1", "Father1", "Assefa")
    assert head["is_household_head"] is True and farmers["FR-0002"]["is_household_head"] is False
    assert head["foundational_id"] == "502628318720" and head["identity_document_type"] == "FAYDA"
    assert (head["region_name"], head["kebele_name"]) == ("Tigray", "Badme")
    assert head["geo_code_hierarchy_json"]["lowest_level_value_id"] == "ET01010102"
    assert head["geo_code_hierarchy_json"]["hierarchy"][-1]["level_value_mnemonic"] == "Badme"
    assert head["created_by"] == head["last_approved_by"] == "seeder" and head["record_status"] == "ACTIVE"
    phone = rows["g2p_register_farmer_phones"][0]
    assert (phone["phone_number"], phone["phone_e164"], phone["country_code"]) == \
        ("941923320", "+251941923320", "ET")
    lands = {r["functional_record_id"]: r for r in rows["g2p_register_lands"]}
    assert sorted(lands) == ["LAND-0001-1", "LAND-0001-2"]
    assert all(r["link_internal_record_id"] == head["internal_record_id"] for r in lands.values())
    assert rows["g2p_register_crops"][0]["link_internal_record_id"] == lands["LAND-0001-1"]["internal_record_id"]
    assert rows["g2p_register_livestocks"][0]["link_internal_record_id"] == lands["LAND-0001-2"]["internal_record_id"]
    assert rows["g2p_register_membership_details"][0]["link_internal_record_id"] == head["internal_record_id"]
    members = [m for m in rows["g2p_register_household_members"] if m["link_internal_record_id"] == first["internal_record_id"]]
    assert [(m["is_head"], m["relationship_to_the_head"]) for m in members] == [(True, "SELF"), (False, "CHILD")]
    assert "land_ref" not in rows["g2p_register_crops"][0]


def test_record_ids_are_the_same_on_every_run(loader):
    assert [r["internal_record_id"] for r in plan(loader)["g2p_register_farmers"]] == \
        [r["internal_record_id"] for r in plan(loader)["g2p_register_farmers"]]


def test_registered_people_are_skipped_and_their_household_is_reused(loader):
    rows = plan(loader, registered={"502628318720"}, member_households={"502628318720": "existing-household"})
    assert [r["functional_record_id"] for r in rows["g2p_register_households"]] == ["HH-0002"]
    assert [r["functional_record_id"] for r in rows["g2p_register_farmers"]] == ["FR-0002", "FR-0003"]
    child = rows["g2p_register_farmers"][0]
    assert child["link_internal_record_id"] == "existing-household" and child["is_household_head"] is False
    assert not rows["g2p_register_lands"]  # the registered person's farm stays as registered
    assert [m["functional_record_id"] for m in rows["g2p_register_household_members"]] == ["HM-0003"]


def test_farm_facts_for_someone_master_data_does_not_hold_fail(loader):
    with pytest.raises(RuntimeError, match="ETH-IND-0099"):
        loader.plan(PEOPLE, HOUSEHOLDS, {**FARMS, "ETH-IND-0099": {}}, loader.Geography(lambda p: CHAIN),
                    set(), {}, NOW)


def test_a_location_master_data_does_not_hold_fails(loader):
    with pytest.raises(RuntimeError, match="geography"):
        loader.plan(PEOPLE, HOUSEHOLDS, FARMS, loader.Geography(lambda p: None), set(), {}, NOW)
