"""The db-seed sample loader: Master Data's sample people plus the pack's farm facts, entered as farmer
intakes and approved at both stages by the sample approvers."""

import ast
import hashlib
import importlib.util
import itertools
import sys
import types
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "docker/db-seed"


@pytest.fixture(scope="module")
def loader():
    stubs = {"psycopg2": types.ModuleType("psycopg2")}
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


def test_loader_signs_in_like_the_portal_and_never_changes_keycloak():
    source = (SEED / "load_sample_data.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    # No password grant, no Keycloak admin API, no direct register writes.
    for forbidden in ("grant_type", "KEYCLOAK_ADMIN", "admin-cli", "/admin/realms", "directAccessGrants",
                      "INSERT INTO", "UPDATE ", "DELETE FROM", "/approve_change_request"):
        assert forbidden not in code, forbidden
    for required in ("/auth/start_authentication_transaction", "kc-form-login", "/auth/callback",
                     "/intake-form-data/finalize_intake_form_submission", "/awe/submit_task_decision",
                     "INTAKE_SEED_APPROVER_1", "INTAKE_SEED_APPROVER_2", "INTAKE_SEED_PASSWORD"):
        assert required in code, required
    imported = {a.name.split(".")[0] for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Import) for a in node.names}
    assert not imported & {"requests", "httpx", "keycloak"}
    client = (SEED / "mds_client.py").read_text(encoding="utf-8")
    assert client.count('"grant_type"') == 1 and '"grant_type": "client_credentials"' in client


def test_master_data_client_is_the_platforms_unchanged():
    digest = hashlib.sha256((SEED / "mds_client.py").read_bytes()).hexdigest()
    assert digest == "2ca03a9c4f40cceb91ad839b272335f47eabee3982685bdd20639dce6bc36c5b"
    dockerfile = (SEED / "Dockerfile").read_text(encoding="utf-8")
    assert "registry-platform docker/db-seed/mds_client.py at e7e6e269" in dockerfile
    assert "ARG OPENG2P_DATA_REPO=https://github.com/Centre-for-Open-Societal-Systems/openg2p-data.git" in dockerfile


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
HOUSEHOLDS = [{"household_id": "ETH-HH-001", "head_individual_id": "ETH-IND-0001", "geo_pcode": "ET01010102"},
              {"household_id": "ETH-HH-002", "head_individual_id": "ETH-IND-0003", "geo_pcode": "ET01010102"}]
FARMER = {"grandfathers_name": "Assefa", "language_spoken": "TIGRINYA", "identity_document_type": "FAYDA",
          "income_sources": ["SOI_CROP_PRODUCTION"], "phone_type": "PRIMARY", "is_farmer": True}
FARMS = {
    "ETH-IND-0001": {
        "individual_id": "ETH-IND-0001", "farmer": FARMER,
        "lands": [{"land_ref": "L1", "land_size": 0.5, "unit": "HECTARE", "current_land_use": "AGRICULTURAL"},
                  {"land_ref": "L2", "land_size": 2, "unit": "TIMAD", "current_land_use": "GRAZING"}],
        "crops": [{"land_ref": "L1", "commodity": "CROP_TEFF", "season": "SEASON_MEHER"}],
        "livestock": [{"land_ref": "L2", "livestock_type": "LSTK_CATTLE", "head_count": 4}],
        "farm_inputs": [{"land_ref": "L1", "fertilizer_use": True}],
        "membership": {"is_primary_cooperative_member": True, "primary_cooperative_name": "Tsehay"},
    },
    "ETH-IND-0002": {"individual_id": "ETH-IND-0002", "farmer": {**FARMER, "grandfathers_name": "Tesfaye"}},
    "ETH-IND-0003": {"individual_id": "ETH-IND-0003", "farmer": {**FARMER, "grandfathers_name": "Kebede"}},
}
TODAY = date(2026, 10, 29)


def plan(loader, farms=FARMS):
    ids = (f"id-{n}" for n in itertools.count(1))
    return loader.plan(PEOPLE, HOUSEHOLDS, farms, loader.Geography(lambda pcode: CHAIN), TODAY,
                       new_id=lambda: next(ids))


def test_each_person_is_one_farmer_intake_heads_first_with_their_household(loader):
    intakes = plan(loader)
    assert [(i["individual_id"], i["is_head"], i["household"]) for i in intakes] == [
        ("ETH-IND-0001", True, "ETH-HH-001"), ("ETH-IND-0002", False, "ETH-HH-001"),
        ("ETH-IND-0003", True, "ETH-HH-002")]
    head, child = intakes[0], intakes[1]
    assert list(head["sections"]) == [s for s in loader.FARMER_SECTIONS if s in head["sections"]]
    assert set(loader.HOUSEHOLD_SECTIONS) <= set(head["sections"])
    assert not set(loader.HOUSEHOLD_SECTIONS) & set(child["sections"])
    household = head["sections"]["household_information"][0]
    assert household["internal_record_id"] == head["household_id"]
    assert (household["size_of_group"], household["number_of_children"], household["number_of_male_members"],
            household["number_of_female_members"]) == (2, 1, 1, 1)
    members = head["sections"]["household_household_household_member_section_02"]
    assert [(m["foundational_id"], m["is_head"], m.get("relationship_to_the_head")) for m in members] == [
        ("502628318720", True, None), ("721996394985", False, "CHILD")]
    assert all(m["link_internal_record_id"] == head["household_id"] for m in members)
    assert child["household_id"] is None and child["sections"]["farmer_household_lookup"] == [
        {"internal_record_id": child["farmer_id"], "is_household_head": False}]


def test_the_farmer_sections_carry_the_person_and_their_farm(loader):
    head = plan(loader)[0]
    s, farmer_id = head["sections"], head["farmer_id"]
    person = s["farmer_personal_details"][0]
    assert {k: person[k] for k in ("internal_record_id", "first_name", "middle_name", "last_name", "language_spoken")} == {
        "internal_record_id": farmer_id, "first_name": "Given1", "middle_name": "Father1",
        "last_name": "Assefa", "language_spoken": "TIGRINYA"}
    assert "farmer_name" not in s
    assert s["farmer_identity"][0]["foundational_id"] == "502628318720"
    assert s["farmer_phones"][0]["phone_number"] == "0941923320"
    assert s["farmer_location"][0]["geo_code_hierarchy_json"]["hierarchy"][-1]["level_value_id"] == "ET01010102"
    assert all(r["link_internal_record_id"] == farmer_id and "land_ref" not in r for r in s["farmer_lands"])
    assert [r.get("area_in_hectare") for r in s["farmer_lands"]] == [0.5, None]
    assert s["farmer_crops_intake"][0]["link_internal_record_id"] == s["farmer_lands"][0]["internal_record_id"]
    assert s["farmer_livestock_intake"][0]["link_internal_record_id"] == s["farmer_lands"][1]["internal_record_id"]
    assert s["farmer_membership"][0]["link_internal_record_id"] == farmer_id
    assert s["farmer_documents"] == [{"internal_record_id": farmer_id, "identity_document_type": "FAYDA"}]
    child = plan(loader)[1]["sections"]
    assert "farmer_lands" not in child and "farmer_membership" not in child


def test_farm_facts_for_someone_master_data_does_not_hold_fail(loader):
    with pytest.raises(RuntimeError, match="ETH-IND-0099"):
        plan(loader, {**FARMS, "ETH-IND-0099": {}})


def test_a_person_without_a_grandfathers_name_fails(loader):
    with pytest.raises(RuntimeError, match="ETH-IND-0002 has no grandfather's name"):
        plan(loader, {**FARMS, "ETH-IND-0002": {"farmer": {}}})


def test_a_location_master_data_does_not_hold_fails(loader):
    with pytest.raises(RuntimeError, match="geography"):
        loader.plan(PEOPLE, HOUSEHOLDS, FARMS, loader.Geography(lambda p: None), TODAY)


class FakeRegistry:
    def __init__(self, farmers=None, awaiting=None):
        self._farmers, self._awaiting = dict(farmers or {}), dict(awaiting or {})
        self.status, self.waited, self.pending = {}, [], []

    def farmers(self):
        return dict(self._farmers)

    def awaiting_approval(self):
        return dict(self._awaiting)

    def approval_status(self, submission_id):
        return self.status.get(submission_id)

    def wait_for(self, table, record_id, timeout):
        self.waited.append((table, record_id))


class FakeApprover:
    """An approver whose task list holds one open task at its stage for every pending intake."""

    def __init__(self, name, stage, registry, calls):
        self.username, self.stage, self.registry, self.calls = name, stage, registry, calls

    def post(self, path, payload):
        self.calls.append((self.username, path))
        if path == "/awe/list_my_tasks":
            return {"data": {"items": [{"id": f"task-{sid}-{self.stage}", "artifact_id": sid,
                                        "stage_order": self.stage} for sid in self.registry.pending]}}
        if path == "/awe/submit_task_decision":
            assert payload["current_stage"] == self.stage and payload["action"] == "approve"
            if self.stage == 2:
                self.registry.status[payload["artifact_id"]] = "APPROVED"
        return {}


def runner(loader, registry, calls):
    run = loader.Loader.__new__(loader.Loader)
    run.registry, run.approve_timeout, run.ingest_timeout = registry, 5, 5
    run.approvers = [FakeApprover("alex.carter", 1, registry, calls), FakeApprover("nina.patel", 2, registry, calls)]
    return run


def run(loader, registry):
    calls, submitted = [], []
    loader_run = runner(loader, registry, calls)

    def submit(intake, household_id):
        sid = f"sub-{intake['individual_id']}"
        submitted.append((intake["individual_id"], household_id, sorted(intake["sections"])))
        registry.pending.append(sid)
        return sid

    loader_run.submit = submit
    return loader_run.run(plan(loader)), submitted, calls


def test_every_intake_is_approved_at_stage_1_then_stage_2_and_members_join_the_heads_household(loader):
    registry = FakeRegistry()
    done, submitted, calls = run(loader, registry)
    assert done == {"registered": 3, "resumed": 0, "skipped": 0}
    (_, _, head_sections), (_, child_household, _), (_, other_household, _) = submitted
    assert child_household == "id-1" and other_household is None  # id-1: the household entered with ETH-IND-0001
    assert "household_information" in head_sections
    decisions = [c for c in calls if c[1] == "/awe/submit_task_decision"]
    assert decisions == [("alex.carter", "/awe/submit_task_decision"), ("nina.patel", "/awe/submit_task_decision")] * 3
    assert ("g2p_register_households", "id-1") in registry.waited


def test_a_rerun_skips_farmers_resumes_waiting_intakes_and_reuses_their_household(loader):
    registry = FakeRegistry(farmers={"502628318720": "registered-household"},
                            awaiting={"721996394985": ("sub-waiting", "farmer-waiting")})
    registry.pending = ["sub-waiting"]
    done, submitted, _ = run(loader, registry)
    assert done == {"registered": 1, "resumed": 1, "skipped": 1}
    assert [s[0] for s in submitted] == ["ETH-IND-0003"]
    assert ("g2p_register_farmers", "farmer-waiting") in registry.waited


def test_a_head_whose_household_a_member_already_joined_does_not_enter_it_again(loader):
    registry = FakeRegistry(farmers={"721996394985": "registered-household"})
    _, submitted, _ = run(loader, registry)
    head = submitted[0]
    assert head[0] == "ETH-IND-0001" and head[1] == "registered-household"
    assert "household_information" not in head[2]


def test_a_member_whose_household_is_not_registered_is_not_entered(loader):
    registry = FakeRegistry()
    members_only = [i for i in plan(loader) if not i["is_head"]]
    with pytest.raises(RuntimeError, match="ETH-HH-001 is not in the register"):
        runner(loader, registry, []).run(members_only)
