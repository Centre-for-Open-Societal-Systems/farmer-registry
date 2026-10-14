"""Guard: the farmer deduplication routes stay behind IAM and CSRF.

The staff API runs ResolvePermissionMiddleware with allow_by_default=True, so a
route that carries no ``@require_permissions`` marker skips token and permission
checks entirely. The three /api/v1/farmer-registry/deduplicate* routes shipped
that way, and were also exempted from CSRF: anyone who could reach the staff API
could rescan the register or wipe every duplicate flag, anonymously and without
an audit event (the audit middleware skips successful anonymous calls).

These tests read app.py as source rather than importing it, so they run on a
developer host without the platform packages. Stdlib only, like the other tests
in this directory.
"""

import ast
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "src" / "openg2p_registry_farmer_extension" / "app.py"

EXPECTED = {
    ("post", "/deduplicate"): {"registryConfiguration:edit"},
    ("get", "/deduplicate/summary"): {"register:view"},
    ("post", "/deduplicate/reset"): {"registryConfiguration:edit"},
}


def _dedup_routes():
    """Map (method, path) -> the permission set declared on that route's handler."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    register = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_register_deduplication_routes"
    )
    routes = {}
    for handler in ast.walk(register):
        if not isinstance(handler, ast.AsyncFunctionDef):
            continue
        route = None
        permissions = None
        for decorator in handler.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "router":
                route = (func.attr, ast.literal_eval(decorator.args[0]))
            elif isinstance(func, ast.Name) and func.id == "require_permissions":
                permissions = set()
                for arg in decorator.args:
                    value = ast.literal_eval(arg)
                    permissions |= {value} if isinstance(value, str) else set(value)
        if route is not None:
            routes[route] = permissions
    return routes


class DedupRouteAuthTest(unittest.TestCase):
    def test_every_route_declares_its_permissions(self):
        self.assertEqual(_dedup_routes(), EXPECTED)

    def test_csrf_is_not_bypassed(self):
        source = APP.read_text(encoding="utf-8")
        self.assertNotIn("_should_skip", source)
        self.assertNotIn("CsrfMiddleware", source)


if __name__ == "__main__":
    unittest.main()
