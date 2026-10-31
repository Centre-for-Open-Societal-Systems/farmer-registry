"""Exercise the real OAN cache loader at fresh-boot clocks without API startup."""

import ast
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "farmer-extension/src/openg2p_registry_farmer_extension/register_domain/services"


def loader():
    # Load the actual function and initial cache literal; framework startup and
    # SQL transport are outside this unit. The hosted worker tests the full path.
    tree = ast.parse((SERVICES / "__init__.py").read_text(encoding="utf-8"))
    initial = next(node.value for node in tree.body if isinstance(node, ast.AnnAssign)
                   and isinstance(node.target, ast.Name) and node.target.id == "_cache")
    functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name in ("_load", "_json")]
    spec = importlib.util.spec_from_file_location("cache_widget_rules", SERVICES / "widget_rules.py")
    widgets = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(widgets)
    state = SimpleNamespace(now=0.0, reads=0, options=["LOAN", "INSURANCE"])

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def execute(self, query):
            state.reads += 1
            await asyncio.sleep(0)  # Make simultaneous cold requests contend.
            if "FROM g2p_register_sections" in query:
                schema = {"widgets": [{"widget": "multi-select", "widget-data-path": "farm-inputs.finance_access_types",
                    "widget-label": "Financial services", "widget-data-source": {"type": "static",
                    "options": [{"value": value} for value in state.options]}}]}
                return SimpleNamespace(all=lambda: [("farm-inputs", json.dumps(schema))])
            if "FROM g2p_register_definitions" in query:
                return SimpleNamespace(all=lambda: [("FarmInputs", "farm-inputs")])
            assert "FROM registry_languages" in query
            return SimpleNamespace(scalar=lambda: "{}")

    namespace = {"Rules": dict, "json": json, "time": SimpleNamespace(monotonic=lambda: state.now),
        "_cache": ast.literal_eval(initial), "_lock": asyncio.Lock(), "_RULES_TTL_SECONDS": 300,
        "dbengine": SimpleNamespace(get=lambda: "synthetic-engine"), "text": lambda query: query,
        "async_sessionmaker": lambda engine: Session, "collect_rules": widgets.collect_rules}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SERVICES / "__init__.py"), "exec"), namespace)
    return namespace["_load"], state, widgets


def test_first_request_at_zero_uptime_loads_and_enforces_declared_choices():
    async def run():
        load, state, widgets = loader()
        rules, registers, _ = await load()
        assert registers == {"FarmInputs": "farm-inputs"}
        errors = widgets.check_record({"finance_access_types": ["LOAN", "UNKNOWN"]}, rules["farm-inputs"])
        assert len(errors) == 1 and "UNKNOWN" in errors[0] and "Financial services" in errors[0]
        assert state.reads == 3
    asyncio.run(run())


def test_concurrent_cold_requests_share_one_complete_metadata_read():
    async def run():
        load, state, _ = loader()
        first, second = await asyncio.gather(load(), load())
        assert first == second and first[1] == {"FarmInputs": "farm-inputs"}
        assert state.reads == 3
    asyncio.run(run())


def test_zero_timestamp_cache_remains_valid_until_expiry_then_refreshes():
    async def run():
        load, state, _ = loader()
        await load()
        state.options = ["LOAN", "INSURANCE", "SAVING"]
        state.now = 299
        rules, _, _ = await load()
        assert rules["farm-inputs"]["finance_access_types"]["options"] == ["LOAN", "INSURANCE"]
        assert state.reads == 3
        state.now = 301
        rules, _, _ = await load()
        assert rules["farm-inputs"]["finance_access_types"]["options"] == state.options
        assert state.reads == 6
    asyncio.run(run())
