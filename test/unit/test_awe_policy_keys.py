"""Guard: the AWE policy keys join across the registry database and the AWE database.

An approval is routed by policy_key across two databases seeded by different files:
  * registry: g2p_registry_awe_policy_configurations binds a register or intake form to a policy_key
    (meta_data/awe-integration/, re-keyed by meta_data/site-configuration/55_default_approvals.sql on the same config ids)
  * AWE: approval_policy, approval_stage and approver_rule (awe_meta_data/)
Nothing checks the join at runtime: a binding to a key the AWE does not have leaves the change request or intake
without an approval, and the stage and rule seeds insert through a JOIN on policy_key and stage_order, so a
mistyped key or order inserts nothing.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "farmer-extension/src/openg2p_registry_farmer_extension/meta_data"
AWE = ROOT / "farmer-extension/src/openg2p_registry_farmer_extension/awe_meta_data"
ID = r"'([0-9a-f-]+)'"


def register_ids():
    """The register ids defined by the register definitions, upstream's and OAN's."""
    paths = [META / "register-metadata/g2p_register_definitions.sql", *sorted(META.glob("site-configuration/05_*.sql"))]
    return {i for path in paths for i in re.findall(rf"\(\s*{ID}\s*,\s*'[A-Za-z]+'", path.read_text())}


def bindings():
    """{config id: (scope, register id, intake form id, policy type, policy key)} after the seed has run."""
    found = {}
    # The seed replays meta_data in path order, so site-configuration's row for a config id is the one that stays.
    for path in sorted(META.rglob("*.sql")):
        text = path.read_text()
        if "g2p_registry_awe_policy_configurations" not in text:
            continue
        for config_id, scope, register_id, form_id, _, policy_type, policy_key in re.findall(
                rf"\(\s*{ID},\s*'(REGISTER|INTAKE_FORM|SECTION)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)',"
                rf"\s*'([^']*)',\s*'([^']*)'", text):
            found[config_id] = (scope, register_id, form_id, policy_type, policy_key)
    return found


def test_registry_bindings_join_the_awe_policies():
    bound = bindings()
    assert len(bound) >= 4, bound
    policies = {key: (status, artifact) for _, key, status, artifact in re.findall(
        rf"\({ID},'([^']+)',\d+,'[^']*',[^,]*,'([a-z]+)','([^']+)'", (AWE / "10_approval_policy.sql").read_text())}
    stages = set(re.findall(rf"\({ID},'([^']+)',(\d+),'[^']*'\)", (AWE / "20_approval_stage.sql").read_text()))
    stages = {(key, order) for _, key, order in stages}
    rules = {(key, order) for _, key, order in
             re.findall(rf"\({ID},'([^']+)',(\d+),'\{{", (AWE / "30_approver_rule.sql").read_text())}
    forms = dict(re.findall(rf"^\({ID},{ID}", (META / "register-metadata/g2p_intake_form_definitions.sql")
                            .read_text(), re.M))
    assert policies and stages and rules and forms

    problems = []
    for config_id, (scope, register_id, form_id, policy_type, key) in sorted(bound.items()):
        if register_id not in register_ids():
            problems.append((config_id, "unknown register", register_id))
        if scope == "INTAKE_FORM" and forms.get(form_id) != register_id:
            problems.append((config_id, "intake form not of this register", form_id))
        if key not in policies:
            problems.append((config_id, "no AWE policy", key))
        elif policies[key] != ("active", policy_type):
            problems.append((config_id, "policy not active or of another artifact type", key, policies[key]))
        elif not any(k == key for k, _ in stages):
            problems.append((config_id, "policy has no stage", key))
    problems += [("stage", "no AWE policy", key) for key, _ in stages if key not in policies]
    problems += [("rule", "no such stage", key, order) for key, order in rules if (key, order) not in stages]
    problems += [("stage", "no approver rule", key, order) for key, order in stages if (key, order) not in rules]
    assert not problems, problems
