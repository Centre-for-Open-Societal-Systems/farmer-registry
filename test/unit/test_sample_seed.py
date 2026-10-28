"""The db-seed's sample loader: pack people and farm facts into form records."""
import importlib.util
import sys
import types
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def loader():
    # The image provides psycopg2 and OpenG2P's loader; the record logic needs neither.
    stubs = {"psycopg2": types.ModuleType("psycopg2"), "psycopg2.extras": types.ModuleType("psycopg2.extras"),
             "openg2p_sample_loader": types.ModuleType("openg2p_sample_loader")}
    stubs["psycopg2"].extras = stubs["psycopg2.extras"]
    stubs["psycopg2.extras"].RealDictCursor = object
    stubs["openg2p_sample_loader"]._address_line = lambda parts: ", ".join(p for p in parts or [] if p)
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("oan_sample_seed", ROOT / "docker/db-seed/load_sample_data.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


GEO = {
    "ET01": {"level_id": 1, "level_mnemonic": "region", "level_value_mnemonic": "Tigray", "parent_level_value_id": None},
    "ET0101": {"level_id": 2, "level_mnemonic": "zone", "level_value_mnemonic": "Central", "parent_level_value_id": "ET01"},
}


def person(individual_id, household_id, relationship, gender="MALE", born=date(1980, 5, 1), nid=None):
    return {"individual_id": individual_id, "household_id": household_id, "given_name": "Given" + individual_id,
            "fathers_name": "Father" + individual_id, "relationship_to_head": relationship, "gender": gender,
            "birth_date": born, "national_id": nid or "FAN" + individual_id, "geo_pcode": "ET0101",
            "phone": "+251911000000", "country": "ETH"}


def test_geo_location_is_the_staff_portal_hierarchy_from_region_down(loader):
    value = loader.geo_location(GEO, "ET0101")
    assert value["geo_lowest_level_value_id"] == "ET0101"
    chain = value["geo_code_hierarchy_json"]["hierarchy"]
    assert [unit["level_value_id"] for unit in chain] == ["ET01", "ET0101"]
    assert chain[0]["level_mnemonic"] == "region"


def test_geo_location_refuses_a_pcode_outside_the_published_geography(loader):
    with pytest.raises(RuntimeError, match="ET99"):
        loader.geo_location(GEO, "ET99")


def test_section_fields_are_the_widget_paths_on_the_sections_register(loader):
    schema = {"elements": [{"widget-data-path": "reg-1.first_name"},
                           {"widget-data-path": {"value": "reg-1.geo_lowest_level_value_id", "other": "reg-2.x"}},
                           [{"widget-data-path": "reg-1.gender"}]]}
    assert set(loader.section_fields(schema, "reg-1")) == {"first_name", "geo_lowest_level_value_id", "gender"}


def test_form_sections_are_selected_by_register_and_written_fields(loader):
    rows = [{"form_id": "f", "register_id": "r", "section_id": sid, "section_register_id": reg,
             "register_mnemonic": mnemonic, "section_ui_schema": {"widget-data-path": f"{reg}.{field}"}}
            for sid, reg, mnemonic, field in (("s1", "r", "Farmer", "first_name"), ("s2", "r", "Farmer", "gender"),
                                              ("s3", "p", "FarmerPhone", "phone_number"))]
    form = loader.Form(rows, "farmer_ingestion_intake")
    assert [s["section_id"] for s in form.sections_of("Farmer")] == ["s1", "s2"]
    assert [s["section_id"] for s in form.sections_of("Farmer", ["gender"])] == ["s2"]
    with pytest.raises(RuntimeError):
        form.sections_of("Land")
    with pytest.raises(RuntimeError, match="not in the registry metadata"):
        loader.Form([], "missing_form")


def test_plan_attaches_names_and_farms_and_requires_a_known_head(loader):
    people = [person("I1", "H1", "SELF"), person("I2", "H1", "CHILD", born=date(2015, 1, 1))]
    farms = {"I1": {"farmer": {"grandfathers_name": "Grand"}}}
    [(_household, members, head)] = loader.plan(people, [{"household_id": "H1", "head_individual_id": "I1"}], farms)
    assert head["name"] == ("GivenI1", "FatherI1", "Grand")
    assert members[1]["name"] == ("GivenI2", "FatherI2", "")
    with pytest.raises(RuntimeError, match="H2"):
        loader.plan([person("I3", "H2", "SPOUSE")], [{"household_id": "H2", "head_individual_id": "I9"}], {})


def test_household_record_counts_members_as_the_intake_rule_requires(loader):
    members = [person("I1", "H1", "SELF"), person("I2", "H1", "SPOUSE", gender="FEMALE"),
               person("I3", "H1", "CHILD", born=date(2020, 1, 1)), person("I4", "H1", "PARENT", born=date(1940, 1, 1))]
    loader.plan(members, [{"household_id": "H1", "head_individual_id": "I1"}], {})
    record = loader.household_record({"geo_pcode": "ET0101", "country": "ETH"}, members, members[0], GEO)
    assert record["size_of_group"] == 4
    assert (record["number_of_male_members"], record["number_of_female_members"]) == (3, 1)
    assert (record["number_of_children"], record["number_of_elderly_members"]) == (1, 1)
    assert record["household_head"] == "GivenI1 FatherI1"
    assert record["country_code"] == "ET"


def test_farmer_record_links_the_household_and_carries_the_pack_farm_facts(loader):
    head = person("I1", "H1", "SELF")
    head["farm"] = {"farmer": {"grandfathers_name": "Grand", "phone_type": "PRIMARY", "is_psnp_user": True}}
    head["name"] = loader.full_name(head, head["farm"])
    record = loader.farmer_record(head, "household-row", GEO)
    assert record["link_internal_record_id"] == "household-row"
    assert record["is_household_head"] is True
    assert record["foundational_id"] == "FANI1" and record["has_national_id"] is True
    assert record["last_name"] == "Grand"
    assert record["is_psnp_user"] is True
    assert "grandfathers_name" not in record and "phone_type" not in record
    assert loader.phone_rows(head) == [{"phone_type": "PRIMARY", "phone_number": "+251911000000",
                                        "country_code": "ET", "is_primary": True}]


def test_seed_image_takes_farm_samples_only_from_openg2p_data_at_a_pinned_commit():
    dockerfile = (ROOT / "docker/db-seed/Dockerfile").read_text()
    assert "ARG OPENG2P_DATA_REF=" in dockerfile and "sha256sum -c" in dockerfile
    ref = dockerfile.split("ARG OPENG2P_DATA_REF=")[1].split()[0]
    assert len(ref) == 40, "pin a commit, not a branch"
    assert not (ROOT / "docker/db-seed/seed-data").exists()
    overlay = (ROOT / "helm/environments/dev/farmer-samples.yaml").read_text()
    assert "loadSampleData: true" in overlay


def test_staging_never_loads_samples():
    spec = importlib.util.spec_from_file_location("deployment", ROOT / "ci/deploy/deployment.py")
    deployment = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deployment)
    assert deployment.samples_overlay("staging") == {}
    assert deployment.samples_overlay("dev")["registry"]["dbSeed"]["loadSampleData"] is True


def test_login_prepares_the_sample_approvers_only_when_keycloak_refuses(loader, monkeypatch):
    base = loader.base
    settings = {"STAFF_TOKEN_URL": "t", "STAFF_CLIENT_ID": "staff", "STAFF_CLIENT_SECRET": "s",
                "INTAKE_SEED_PASSWORD": "p", "STAFF_API_URL": "api", "KEYCLOAK_BASE_URL": "kc",
                "KEYCLOAK_REALM": "staff", "KEYCLOAK_ADMIN_USER": "admin", "KEYCLOAK_ADMIN_PASSWORD": "pw"}
    prepared = []
    ready = {"value": False}

    def fetch_token(url, client_id, user, password, secret):
        if not ready["value"]:
            raise RuntimeError(f"password grant failed for '{user}' (400): not_allowed")
        return "token-" + user

    def prepare(*args):
        prepared.append(args)
        ready["value"] = True

    monkeypatch.setattr(base, "env", lambda name, default=None, required=False: settings.get(name, default), raising=False)
    monkeypatch.setattr(base, "fetch_token", fetch_token, raising=False)
    monkeypatch.setattr(base, "keycloak_prepare_users", prepare, raising=False)
    monkeypatch.setattr(base, "StaffClient", lambda api, token, user, token_provider: (user, token), raising=False)

    client, clients = loader.staff_clients()
    assert client == ("alex.carter", "token-alex.carter")
    assert set(clients) == {"alex.carter", "nina.patel"}
    assert prepared == [("kc", "staff", "admin", "pw", "staff", ["alex.carter", "nina.patel"], "p")]

    prepared.clear()
    loader.staff_clients()
    assert prepared == [], "a working login changes nothing in Keycloak"


def test_farmer_record_takes_the_head_answer_the_household_allows(loader):
    head = person("I1", "H1", "SELF")
    head["farm"] = {}
    head["name"] = loader.full_name(head, head["farm"])
    assert loader.farmer_record(head, "hh", GEO)["is_household_head"] is True
    assert loader.farmer_record(head, "hh", GEO, is_head=False)["is_household_head"] is False
    assert loader.same_name(" GivenI1  FatherI1 ", "giveni1 fatheri1")
