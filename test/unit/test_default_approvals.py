"""Farmer approvals: two sequential OpenG2P stages, each completed by the named officer or admin."""
from pathlib import Path
import re
import json

ROOT = Path(__file__).resolve().parents[2]
OAN_SEEDS = ROOT / "farmer-extension/src/openg2p_registry_farmer_extension/awe_meta_data/zz-oan"
KEYS = ("registry.change_request.farmer.default", "registry.change_request.household.default",
        "registry.intake_form.farmer.default", "registry.intake_form.household.default")
ADMIN_RULE = '{"user_id": "admin"}'


def test_native_farmer_policy_is_carried_unmodified():
    base = ROOT / "sample-farmer-extension/src/openg2p_registry_farmer_extension/awe_meta_data"
    stage = (base / "20_approval_stage.sql").read_text()
    rules = (base / "30_approver_rule.sql").read_text()
    for key in ("registry.change_request.farmer", "registry.change_request.household",
                "registry.intake_form.farmer", "registry.intake_form.household"):
        for order, user in ((1, "alex.carter"), (2, "nina.patel")):
            assert re.search(re.escape("'" + key + "'") + rf", {order}, 'Stage {order} Officers', 'all'", stage)
            assert re.search(re.escape("'" + key + "'") + rf", {order}, 'user',.*" + re.escape(user), rules)
    assert "'block'" in stage
    runtime = (ROOT / "farmer-extension/src/openg2p_registry_farmer_extension/runtime.py").read_text()
    assert "geo_approval" not in runtime


def test_each_stage_is_completed_by_the_named_officer_or_admin():
    policies = json.loads((ROOT / "docs/default-awe-policies.json").read_text())
    assert sorted(p["policy_key"] for p in policies) == sorted(KEYS)
    for policy in policies:
        assert policy["forbid_self_approval"] is False
        assert policy["forbid_repeat_approvers"] is False
        assert [s["stage_order"] for s in policy["stages"]] == [1, 2]
        for stage, user in zip(policy["stages"], ("alex.carter", "nina.patel")):
            assert stage["mode"] == "any-n" and stage["mode_value"] == 1 and stage["on_empty"] == "block"
            assert stage["rules"] == [
                {"rule_type": "user", "rule_value": {"user_id": user}, "kind": "approver", "required": False},
                {"rule_type": "user", "rule_value": {"user_id": "admin"}, "kind": "approver", "required": False}]
    stage_sql = (OAN_SEEDS / "20_approval_stage.sql").read_text()
    rule_sql = (OAN_SEEDS / "30_approver_rule.sql").read_text()
    assert "'all'" not in stage_sql and stage_sql.count("'any-n',1,") == 1
    for key in KEYS:
        for order, user in ((1, "alex.carter"), (2, "nina.patel")):
            assert re.search(re.escape("'" + key + "'") + rf",{order},'Stage {order} Officers'", stage_sql)
            named = '{"user_id": "' + user + '"}'
            assert re.search(re.escape("'" + key + "'") + rf",{order},'" + re.escape(named), rule_sql)
            assert re.search(re.escape("'" + key + "'") + rf",{order},'" + re.escape(ADMIN_RULE), rule_sql)
    assert rule_sql.count('"admin"') == 8
    ids = set(re.findall(r"\('([0-9a-f-]{36})'", rule_sql))
    assert len(ids) == 16, "every approver rule needs its own stable id"


def test_existing_databases_are_moved_in_place_and_nothing_else_is_rewritten():
    files = sorted(p.name for p in OAN_SEEDS.iterdir() if p.is_file())
    assert files == ["10_approval_policy.sql", "20_approval_stage.sql", "30_approver_rule.sql",
                     "50_either_officer_or_admin.sql"]
    update = (OAN_SEEDS / "50_either_officer_or_admin.sql").read_text()
    stage_sql = (OAN_SEEDS / "20_approval_stage.sql").read_text()
    seeded_stage_ids = re.findall(r"\('([0-9a-f-]{36})','registry\.", stage_sql)
    assert len(seeded_stage_ids) == 8
    assert update.count("UPDATE public.approval_stage SET mode='any-n', mode_value=1") == 1
    for stage_id in seeded_stage_ids:
        assert stage_id in update
    assert "DELETE FROM" not in update and "approver_rule" not in update and "approval_policy" not in update
    others = "\n".join((OAN_SEEDS / n).read_text() for n in files if n != "50_either_officer_or_admin.sql")
    assert "DELETE FROM" not in others and "UPDATE public." not in others
    bindings = (ROOT / "farmer-extension/src/openg2p_registry_farmer_extension/meta_data/zz-oan/55_default_approvals.sql").read_text()
    assert "context_field_names=NULL" in bindings
    # The seed carries the Farmer callback registration and OAN's policy only;
    # OpenG2P's Farmer policy files (sample-farmer-extension) are not shipped.
    carried = sorted(p.name for p in OAN_SEEDS.parent.iterdir() if p.is_file())
    assert carried == ["40_callback_secret.sql.tpl"]
    dockerfile = (ROOT / "docker/db-seed/Dockerfile").read_text()
    assert re.search(r"^COPY farmer-extension/src/openg2p_registry_farmer_extension/awe_meta_data/\s+/seed/awe_meta_data/$", dockerfile, re.M)
