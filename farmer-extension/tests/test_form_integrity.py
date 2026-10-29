"""Tests for the condition engine and the Fayda ID check (form_integrity.py).

The pure part has no framework imports, so it is loaded from the services
directory without the package's __init__ and these tests run without the
registry installed:

    uv run --no-project --with pytest pytest farmer-extension/tests
"""

import importlib
import sys
import types
from pathlib import Path

_DIR = Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension/register_domain/services"
_package = types.ModuleType("oan_services_pure")
_package.__path__ = [str(_DIR)]
sys.modules.setdefault("oan_services_pure", _package)
fi = importlib.import_module("oan_services_pure.form_integrity")

FARMER = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"


def _w(widget_id, kind="text", required=False, options=None, path=None, label=None):
    widget = {"widget": kind, "widget-id": widget_id, "widget-label": label or widget_id,
              "widget-required": required, "widget-data-path": path or f"{FARMER}.{widget_id}"}
    if options:
        widget["widget-data-options"] = options
    return widget


def _equals(field, value):
    return {"field": f"{FARMER}.{field}", "operator": "equals", "value": value}


def test_conditions_match_the_ui_engine():
    values = {FARMER: {"flag": True, "text": "TRUE", "n": 3, "blank": "", "items": ["A"]}}
    match = fi.condition_matches
    assert match(_equals("flag", True), values)
    assert not match(_equals("text", True), values)  # a boolean value needs a boolean field
    assert match(_equals("flag", "yes"), values)  # a boolean field takes a boolean-like value
    assert match({"field": f"{FARMER}.blank", "operator": "empty"}, values)
    assert not match({"field": f"{FARMER}.blank", "operator": "notEmpty"}, values)
    assert match({"field": f"{FARMER}.n", "operator": "greaterThan", "value": 2}, values)
    assert match({"field": f"{FARMER}.items", "operator": "contains", "value": "A"}, values)
    assert match({"field": f"{FARMER}.items", "operator": "notContains", "value": "B"}, values)
    assert not match({"field": f"{FARMER}.n", "operator": "unknown"}, values)


def test_the_last_show_or_hide_rule_wins():
    widget = _w("x", options={"actions": [{"action": "hide", "condition": _equals("a", True)},
                                         {"action": "show", "condition": _equals("b", True)}]})
    assert fi.widget_state(widget, {FARMER: {"a": True, "b": True}}) == (True, False)
    assert fi.widget_state(widget, {FARMER: {"a": True, "b": False}}) == (False, False)


def test_fayda_ids_compare_without_spaces():
    assert fi.fayda_id(" 0012 3456 7890 1234 ") == "0012345678901234"
    assert fi.fayda_id("   ") is None
    assert fi.fayda_id(None) is None


def test_the_holder_is_named_by_record_name_or_names():
    assert fi.holder_name({"record_name": "Abebe Kebede"}) == "Abebe Kebede"
    assert fi.holder_name({"first_name": "Abebe", "middle_name": None, "last_name": "Kebede"}) == "Abebe Kebede"
    assert fi.holder_name({}) == "an unnamed farmer"
