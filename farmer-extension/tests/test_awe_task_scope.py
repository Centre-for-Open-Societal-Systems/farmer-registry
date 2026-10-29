"""Approval task lists show only this registry's tasks.

The approval workflow engine is shared by every registry, so the platform's
task list and counters return all of them. The scoped service keeps the tasks
whose policy key comes from this registry's own approval seed.
"""
import asyncio
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

PACKAGE_NAME = "openg2p_registry_farmer_extension"
PACKAGE = Path(__file__).resolve().parents[1] / "src" / PACKAGE_NAME
OWN = ['registry.change_request.farmer','registry.change_request.farmer.default','registry.change_request.household','registry.change_request.household.default','registry.intake_form.farmer','registry.intake_form.farmer.default','registry.intake_form.household','registry.intake_form.household.default']
FOREIGN = ['registry.change_request.cropsown.default','registry.change_request.cropsown-farmer.default','registry.intake_form.cropsown.default','registry.change_request.livestock.default','registry.change_request.livestock-farmer.default','registry.intake_form.livestock.default']


def _load(name, path, package=None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if package:
        module.__package__ = package
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Absolute-name load: the module has no relative imports and no platform imports.
scope_module = _load("awe_task_scope_under_test", PACKAGE / "awe_task_scope.py")


def run(coroutine):
    return asyncio.run(coroutine)


def task(index, policy_key, artifact_type=None):
    kind = artifact_type
    if kind is None:
        kind = ("registry.change_request" if ".change_request." in policy_key
                else "registry.intake_form")
    return {"id": f"t{index}", "policy_key": policy_key, "artifact_type": kind,
            "artifact_id": f"a{index}", "status": "open"}


class FakeHelper:
    """Serves tasks in pages of at most 100, as the engine does."""

    def __init__(self, tasks):
        self.tasks = tasks
        self.calls = []

    async def list_my_tasks(self, token, **filters):
        self.calls.append(filters)
        size = min(filters["page_size"], 100)
        page = filters["page"]
        rows = [t for t in self.tasks
                if filters.get("status") in (None, t["status"])
                and filters.get("artifact_type") in (None, t["artifact_type"])
                and filters.get("policy_key") in (None, t["policy_key"])]
        total = len(rows)
        return {"items": rows[(page - 1) * size: page * size], "total": total,
                "page": page, "page_size": size, "pages": -(-total // size) or 1}


class Payload:
    def __init__(self, **values):
        self.request_id = None
        self.status = None
        self.artifact_type = None
        self.policy_key = None
        self.search_text = None
        self.page = 1
        self.page_size = 25
        self.__dict__.update(values)


class FakeCore:
    """Stands in for the platform service the mixin sits in front of."""

    passthrough = []

    async def list_my_tasks(self, payload, *, bearer_token):
        self.passthrough.append(("list", payload.policy_key))
        return {"items": ["platform"], "total": 1, "page": 1, "page_size": 25, "pages": 1}

    async def my_task_stats(self, payload, *, bearer_token):
        self.passthrough.append(("stats", payload.status))
        return {"total": 999, "change_request_count": 500, "intake_form_count": 499, "other": 7}


def make_service(tasks, package_dir=PACKAGE, configured=()):
    class Service(scope_module.ScopedAweTasksMixin, FakeCore):
        scope_package_dir = package_dir
        helper = FakeHelper(tasks)

        def _awe_helper(self):
            return self.helper

        async def _configured_policy_keys(self):
            return configured

    FakeCore.passthrough = []
    return Service()


def mixed_tasks(own_count=130, foreign_count=70):
    tasks = []
    for index in range(own_count):
        tasks.append(task(index, OWN[index % len(OWN)]))
    for index in range(foreign_count):
        tasks.append(task(1000 + index, FOREIGN[index % len(FOREIGN)]))
    # interleave so no page is all one registry
    return sorted(tasks, key=lambda t: int(t["id"][1:]) * 37 % 101)


class SeedScopeTests(unittest.TestCase):
    def test_every_seeded_key_is_owned(self):
        scope = scope_module.PolicyScope(scope_module.seeded_policy_keys(PACKAGE))
        for key in OWN:
            self.assertTrue(scope.owns(key), key)

    def test_other_registries_keys_are_not_owned(self):
        scope = scope_module.PolicyScope(scope_module.seeded_policy_keys(PACKAGE))
        for key in FOREIGN:
            self.assertFalse(scope.owns(key), key)

    def test_variant_of_own_key_is_owned_and_lookalike_is_not(self):
        scope = scope_module.PolicyScope(scope_module.seeded_policy_keys(PACKAGE))
        domain = sorted(scope.domains)[0]
        self.assertTrue(scope.owns(f"registry.change_request.{domain}.v2"))
        self.assertFalse(scope.owns(f"registry.change_request.{domain}x.default"))
        self.assertFalse(scope.owns(None))
        self.assertFalse(scope.owns("unrelated"))


class ListMyTasksTests(unittest.TestCase):
    def test_foreign_tasks_are_dropped_and_total_counts_own_only(self):
        service = make_service(mixed_tasks())
        result = run(service.list_my_tasks(Payload(page_size=100), bearer_token="t"))
        self.assertEqual(result["total"], 130)
        self.assertEqual(len(result["items"]), 100)
        self.assertTrue(all(t["policy_key"] in OWN for t in result["items"]))
        self.assertEqual(result["pages"], 2)

    def test_second_page_holds_the_remainder_and_nothing_repeats(self):
        service = make_service(mixed_tasks())
        first = run(service.list_my_tasks(Payload(page=1, page_size=100), bearer_token="t"))
        second = run(service.list_my_tasks(Payload(page=2, page_size=100), bearer_token="t"))
        self.assertEqual(len(second["items"]), 30)
        ids = [t["id"] for t in first["items"] + second["items"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_engine_page_is_read_with_the_capped_page_size(self):
        service = make_service(mixed_tasks())
        run(service.list_my_tasks(Payload(), bearer_token="t"))
        sizes = {c["page_size"] for c in service.helper.calls}
        self.assertEqual(sizes, {100})
        self.assertEqual([c["page"] for c in service.helper.calls], [1, 2])

    def test_status_and_artifact_type_filters_reach_the_engine(self):
        service = make_service(mixed_tasks())
        run(service.list_my_tasks(
            Payload(status="open", artifact_type="registry.change_request"), bearer_token="t"))
        self.assertEqual(service.helper.calls[0]["status"], "open")
        self.assertEqual(service.helper.calls[0]["artifact_type"], "registry.change_request")

    def test_no_own_tasks_gives_an_empty_page(self):
        service = make_service([task(1, FOREIGN[0])])
        result = run(service.list_my_tasks(Payload(), bearer_token="t"))
        self.assertEqual((result["items"], result["total"], result["pages"]), ([], 0, 1))

    def test_own_policy_key_filter_goes_to_the_platform(self):
        service = make_service(mixed_tasks())
        result = run(service.list_my_tasks(Payload(policy_key=OWN[0]), bearer_token="t"))
        self.assertEqual(result["items"], ["platform"])
        self.assertEqual(FakeCore.passthrough, [("list", OWN[0])])

    def test_foreign_policy_key_filter_is_empty_without_asking_the_engine(self):
        service = make_service(mixed_tasks())
        result = run(service.list_my_tasks(Payload(policy_key=FOREIGN[0]), bearer_token="t"))
        self.assertEqual((result["items"], result["total"]), ([], 0))
        self.assertEqual(service.helper.calls, [])
        self.assertEqual(FakeCore.passthrough, [])

    def test_key_configured_in_the_database_is_owned(self):
        legacy = "registry.change_request.legacy-key"
        service = make_service([task(1, legacy), task(2, FOREIGN[0])], configured=[legacy])
        result = run(service.list_my_tasks(Payload(), bearer_token="t"))
        self.assertEqual([t["policy_key"] for t in result["items"]], [legacy])

    def test_unreadable_seed_leaves_the_platform_listing_untouched(self):
        with tempfile.TemporaryDirectory() as empty:
            service = make_service(mixed_tasks(), package_dir=Path(empty))
            result = run(service.list_my_tasks(Payload(), bearer_token="t"))
        self.assertEqual(result["items"], ["platform"])


class StatsTests(unittest.TestCase):
    def test_counts_cover_own_tasks_only(self):
        tasks = mixed_tasks()
        service = make_service(tasks)
        stats = run(service.my_task_stats(Payload(), bearer_token="t"))
        own = [t for t in tasks if t["policy_key"] in OWN]
        self.assertEqual(stats["total"], len(own))
        self.assertEqual(stats["change_request_count"],
                         sum(t["artifact_type"] == "registry.change_request" for t in own))
        self.assertEqual(stats["intake_form_count"],
                         sum(t["artifact_type"] == "registry.intake_form" for t in own))
        self.assertEqual(stats["total"], stats["change_request_count"] + stats["intake_form_count"])
        self.assertEqual(stats["other"], 7)

    def test_status_filter_is_honoured(self):
        tasks = mixed_tasks(own_count=20, foreign_count=0)
        for item in tasks[:5]:
            item["status"] = "completed"
        service = make_service(tasks)
        stats = run(service.my_task_stats(Payload(status="open"), bearer_token="t"))
        self.assertEqual(stats["total"], 15)


class InstallTests(unittest.TestCase):
    """Registration puts one instance at the platform service's position."""

    def setUp(self):
        class Core:
            def __init__(self):
                registry.append(self)

            async def list_my_tasks(self, payload, *, bearer_token):
                return {}

            async def my_task_stats(self, payload, *, bearer_token):
                return {}

            @staticmethod
            def _wrap_awe_error(exc):
                return exc

        registry = []
        self.registry = registry
        self.core = Core
        stubs = {
            "openg2p_fastapi_common": types.ModuleType("openg2p_fastapi_common"),
            "openg2p_fastapi_common.context": types.SimpleNamespace(
                component_registry=registry, get_async_session_maker=lambda: None),
            "openg2p_registry_core": types.ModuleType("openg2p_registry_core"),
            "openg2p_registry_core.controller_services": types.SimpleNamespace(
                G2PAweProxyControllerService=Core),
            "openg2p_registry_core.helpers": types.SimpleNamespace(
                AWEClientError=Exception, AweHelper=object),
            "sqlalchemy": types.SimpleNamespace(text=lambda sql: sql),
        }
        patcher = mock.patch.dict(sys.modules, stubs)
        patcher.start()
        self.addCleanup(patcher.stop)
        package = types.ModuleType("scoped_pkg")
        package.__path__ = [str(PACKAGE)]
        sys.modules["scoped_pkg"] = package
        self.addCleanup(sys.modules.pop, "scoped_pkg", None)
        _load("scoped_pkg.awe_task_scope", PACKAGE / "awe_task_scope.py", "scoped_pkg")
        self.addCleanup(sys.modules.pop, "scoped_pkg.awe_task_scope", None)
        self.proxy = _load("scoped_pkg.awe_proxy", PACKAGE / "awe_proxy.py", "scoped_pkg")
        self.addCleanup(sys.modules.pop, "scoped_pkg.awe_proxy", None)

    def test_install_takes_the_platform_position_once(self):
        platform = self.core()
        other = object()
        self.registry.insert(0, other)
        self.proxy.install()
        self.proxy.install()
        scoped = [i for i in self.registry if isinstance(i, self.proxy.ScopedAweProxyControllerService)]
        self.assertEqual(len(scoped), 1)
        self.assertEqual(self.registry.index(scoped[0]) + 1, self.registry.index(platform))
        first = next(i for i in self.registry if isinstance(i, self.core))
        self.assertIs(first, scoped[0])

    def test_service_reads_this_packages_seed(self):
        self.assertEqual(self.proxy.ScopedAweProxyControllerService.scope_package_dir, PACKAGE)


if __name__ == "__main__":
    unittest.main()
