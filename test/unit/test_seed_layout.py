"""Check dependencies in the platform seed runner's lexical file order."""

from pathlib import Path


EXTENSION = (
    Path(__file__).resolve().parents[2]
    / "farmer-extension/src/openg2p_registry_oan_farmer_extension"
)


def test_site_configuration_runs_after_base_metadata():
    root = EXTENSION / "meta_data"
    paths = sorted(path.relative_to(root).as_posix() for path in root.rglob("*.sql"))
    base = [path for path in paths if not path.startswith("site-configuration/")]
    site = [path for path in paths if path.startswith("site-configuration/")]

    assert base and site
    assert paths == base + site
    assert site.index("site-configuration/88_farmer_tab_text.sql") < site.index(
        "site-configuration/88_readable_text_checks.sql"
    )


def test_approval_seed_runs_in_dependency_order():
    root = EXTENSION / "awe_meta_data"
    paths = sorted(path.relative_to(root).as_posix() for path in root.rglob("*.sql"))

    assert paths == [
        "10_approval_policy.sql",
        "20_approval_stage.sql",
        "30_approver_rule.sql",
        "50_either_officer_or_admin.sql",
    ]
    assert (root / "40_callback_secret.sql.tpl").is_file()
