"""The upstream calendar is vendored without edits until the platform ships it."""

import hashlib
import importlib.util
from pathlib import Path

import pytest

OVERRIDES = Path(__file__).parents[2] / "ui/staff-ui/overrides"
UPSTREAM_FILES = {
    "src/features/activity/components/EthiopianDateInput.tsx": "1c4f40e569e78945af9ecda6d955d961d37eb7d1c07e953a5b61900a0731a8c8",
    "src/features/activity/utils/ethiopianCalendar.ts": "20445c685b8af2277ce2efe533b36aae0124646044fe5a54ed691b279ae5b89c",
}


@pytest.mark.parametrize("path,digest", UPSTREAM_FILES.items())
def test_upstream_calendar_bytes_are_unchanged(path, digest):
    assert hashlib.sha256((OVERRIDES / path).read_bytes()).hexdigest() == digest
    assert digest in (OVERRIDES / "src/features/activity/UPSTREAM.md").read_text()


def test_custom_table_date_keeps_server_date_validation():
    rules_path = Path(__file__).parents[1] / (
        "src/oan_farmer_registry_extension/register_domain/services/widget_rules.py"
    )
    spec = importlib.util.spec_from_file_location("ec_widget_rules", rules_path)
    rules_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rules_module)
    columns = {
        "widget": "table",
        "widget-data-path": "member.records",
        "widget-data-columns": [
            {
                "widget": "oan-ethiopian-date-input",
                "column-key": "birth_date",
                "widget-data-path": "birth_date",
                "widget-required": True,
            }
        ],
    }
    rule = rules_module.collect_rules([("member", columns)])["member"]
    assert rule["birth_date"]["type"] == "date"
    assert rule["birth_date"]["required"] is True
    assert rules_module.check_record({"birth_date": "2020-02-29"}, rule) == []
    assert rules_module.check_record({"birth_date": "2020-02-30"}, rule)
