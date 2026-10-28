"""Farmer retains the unmodified OpenG2P example approval configuration."""
from pathlib import Path
import re
import json

ROOT = Path(__file__).resolve().parents[2]


def test_native_farmer_policy_has_two_all_block_stages_and_default_reviewers():
    base = ROOT / "farmer-extension/src/openg2p_registry_farmer_extension/awe_meta_data"
    stage = (base / "20_approval_stage.sql").read_text()
    rules = (base / "30_approver_rule.sql").read_text()
    for key in ("registry.change_request.farmer", "registry.change_request.household",
                "registry.intake_form.farmer", "registry.intake_form.household"):
        for order, user in ((1, "alex.carter"), (2, "nina.patel")):
            assert re.search(re.escape("'" + key + "'") + rf", {order}, 'Stage {order} Officers', 'all'", stage)
            assert re.search(re.escape("'" + key + "'") + rf', {order}, \'user\',.*' + re.escape(user), rules)
    assert "'block'" in stage
    runtime = (ROOT / "oan-extension/src/openg2p_registry_oan_extension/runtime.py").read_text()
    assert "geo_approval" not in runtime


def test_existing_policy_customizations_cannot_leak_into_the_reset_defaults():
    policies = json.loads((ROOT / "docs/default-awe-policies.json").read_text())
    assert len(policies) == 4
    for policy in policies:
        assert policy["policy_key"].endswith(".default")
        assert policy["forbid_self_approval"] is False
        assert policy["forbid_repeat_approvers"] is False
        assert [s["stage_order"] for s in policy["stages"]] == [1, 2]
        for stage, user in zip(policy["stages"], ("alex.carter", "nina.patel")):
            assert stage["mode"] == "all" and stage["on_empty"] == "block"
            assert stage["rules"] == [{"rule_type":"user", "rule_value":{"user_id":user},
                                       "kind":"approver", "required":False}]
    package = ROOT / "oan-extension/src/openg2p_registry_oan_extension"
    sql = "\n".join(p.read_text() for p in (package / "awe_meta_data").glob("*.sql"))
    assert "DELETE FROM" not in sql and "UPDATE public." not in sql
    bindings = (package / "meta_data/55_default_approvals.sql").read_text()
    assert "context_field_names=NULL" in bindings
    dockerfile = (ROOT / "docker/db-seed/Dockerfile").read_text()
    assert "rm -f /seed/awe_meta_data/10_approval_policy.sql" in dockerfile
    assert "rm -rf /seed/awe_meta_data" not in dockerfile
