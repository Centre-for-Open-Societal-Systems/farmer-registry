"""The dashboard hook rehearsal grants exactly the reviewed staff accounts (scripts/operations/dashboard)."""

import importlib.util
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "rehearse", REPO / "scripts/operations/dashboard/rehearse.py"
)
rehearse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehearse)
DEV_VALUES = REPO / "helm/environments/dev/services/farmer-registry-dashboard.yaml"


def values(tmp_path, users):
    path = tmp_path / "values.yaml"
    path.write_text(
        yaml.safe_dump({"iamSetup": {"grantUsers": users}}), encoding="utf-8"
    )
    return path


def test_the_dev_values_are_a_list_the_rehearsal_accepts():
    users = rehearse.reviewed_grant_users(DEV_VALUES)
    assert users[0] == "admin" and len(users) == len(set(users))


@pytest.mark.parametrize("users", [["admin"], ["admin", "alex.carter", "nina.patel"]])
def test_a_reviewed_list_with_admin_is_accepted_in_order(tmp_path, users):
    assert rehearse.reviewed_grant_users(values(tmp_path, users)) == users


@pytest.mark.parametrize(
    "users",
    [
        None,
        [],
        ["alex.carter"],
        ["admin", "admin"],
        ["admin", "Bad User"],
        ["admin", "x;rm -rf"],
        "admin",
    ],
)
def test_anything_else_fails_closed(tmp_path, users):
    with pytest.raises(ValueError, match="grant-users-not-reviewed"):
        rehearse.reviewed_grant_users(values(tmp_path, users))


def test_the_fixture_knows_every_listed_user_and_only_them():
    source = (REPO / "scripts/operations/dashboard/fixture-server.mjs").read_text(
        encoding="utf-8"
    )
    assert 'process.env.FIXTURE_USERS || "admin"' in source
    assert "fixtureUsers.map(userId).includes(grant[1])" in source
    script = (REPO / "scripts/operations/dashboard/rehearse.py").read_text(
        encoding="utf-8"
    )
    assert (
        "'FIXTURE_USERS='+' '.join(users)" in script
        and "'grants':2+len(users)" in script
    )
