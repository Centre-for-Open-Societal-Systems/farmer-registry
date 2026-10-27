"""An expected popup close must never conceal a browser or identity failure."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "ui/staff-ui/test/popup-flow/run_browser.py"


class PlaywrightError(Exception):
    pass


def helper():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "click_continue")
    namespace = {"PlaywrightError": PlaywrightError}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["click_continue"]


FIN = "001234567890"
CLOSED = "Locator.click: Target page, context or browser has been closed"


class Parent:
    def __init__(self, closed=False, connected=True):
        self.closed = closed
        self.requests = []
        self.context = SimpleNamespace(browser=SimpleNamespace(is_connected=lambda: connected))

    def is_closed(self):
        return self.closed

    def evaluate(self, expression):
        if expression == "window.requests.length":
            return len(self.requests)
        assert expression == "window.requests"
        return self.requests


class Popup:
    def __init__(self, parent, error=None, requests=None, closed=True):
        self.parent, self.error, self.requests, self.closed = parent, error, requests, closed
        self.clicks = 0

    def get_by_role(self, role, **kwargs):
        assert (role, kwargs) == ("button", {"name": "Continue", "exact": True})
        return self

    def click(self):
        self.clicks += 1
        self.parent.requests = self.requests or []
        if self.error:
            raise self.error

    def is_closed(self):
        return self.closed


def request(fin=FIN):
    return [["POST", "synthetic", {}, {"foundational_id": fin}]]


def test_normal_real_click_and_expected_close_both_preserve_action():
    for error in (None, PlaywrightError(CLOSED)):
        page = Parent()
        popup = Popup(page, error, request())
        helper()(popup, page, FIN)
        assert popup.clicks == 1 and page.requests == request()


@pytest.mark.parametrize("mutation", ["parent-closed", "disconnected", "no-browser", "popup-open", "no-request", "wrong-fin", "multiple-requests", "malformed-request", "different-error"])
def test_close_guard_cannot_hide_failures(mutation):
    page = Parent(closed=mutation == "parent-closed", connected=mutation != "disconnected")
    popup = Popup(page, PlaywrightError(CLOSED), request(), closed=mutation != "popup-open")
    if mutation == "no-browser": page.context.browser = None
    if mutation == "no-request": popup.requests = []
    if mutation == "wrong-fin": popup.requests = request("009876543210")
    if mutation == "multiple-requests": popup.requests = request() + request()
    if mutation == "malformed-request": popup.requests = [["POST"]]
    if mutation == "different-error": popup.error = PlaywrightError("Timeout waiting for Continue")
    with pytest.raises(PlaywrightError):
        helper()(popup, page, FIN)
    assert popup.clicks == 1


def test_preexisting_request_is_not_evidence_of_new_dispatch():
    page = Parent()
    page.requests = request()
    popup = Popup(page, PlaywrightError(CLOSED), request())
    with pytest.raises(AssertionError, match="pre-click"):
        helper()(popup, page, FIN)
    assert popup.clicks == 0


def test_non_playwright_exception_is_never_suppressed():
    page = Parent()
    popup = Popup(page, ValueError(CLOSED), request())
    with pytest.raises(ValueError):
        helper()(popup, page, FIN)
