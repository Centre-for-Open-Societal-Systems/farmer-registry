"""Farmer retains the unmodified OpenG2P example approval configuration."""
from pathlib import Path
import re

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
    assert not (ROOT / "oan-extension/src/openg2p_registry_oan_extension/awe_meta_data").exists()
