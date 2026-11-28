"""Keep each registry's approval task list to the registry's own tasks.

Every registry shares one approval workflow engine, so the engine's task list
for a signed-in officer holds the tasks of all registries. The platform proxy
offers no registry filter (only one exact policy key), so a portal would list,
count and open tasks that belong to another registry.

A task belongs to this registry when its policy key is one the registry itself
seeds or has configured. The registry's own approval seed (``awe_meta_data``
and the ``*awe*.sql`` files under ``meta_data``) is read at start-up, so no key
list is repeated in code. The first word of the policy name is the registry's
domain (``registry.change_request.cropsown-farmer.default`` belongs to
``cropsown``, ``registry.intake_form.household`` to ``household``), which also
keeps variants of the seeded keys together. Keys the registry configures in its
own database (``g2p_registry_awe_policy_configurations``) are added at run
time.

This module has no platform imports so it can be tested on its own.
"""
import logging
import math
import re
import time
from pathlib import Path
from typing import Iterable, Optional

_logger = logging.getLogger("oan-awe-task-scope")

CHANGE_REQUEST_ARTIFACT = "registry.change_request"
INTAKE_FORM_ARTIFACT = "registry.intake_form"
_ARTIFACT_PREFIXES = (CHANGE_REQUEST_ARTIFACT + ".", INTAKE_FORM_ARTIFACT + ".")
_POLICY_KEY = re.compile(
    r"""['"](registry\.(?:change_request|intake_form)\.[A-Za-z0-9_.\-]+)['"]"""
)
# The engine caps a page at 100 tasks.
AWE_PAGE_SIZE = 100
# Upper bound on pages read for one listing (10,000 tasks) so a runaway engine
# response cannot loop forever.
MAX_AWE_PAGES = 100
CONFIGURED_KEYS_TTL_SECONDS = 60.0


def _domain(policy_key: str) -> Optional[str]:
    for prefix in _ARTIFACT_PREFIXES:
        if policy_key.startswith(prefix):
            return re.split(r"[.\-_]", policy_key[len(prefix):], maxsplit=1)[0] or None
    return None


class PolicyScope:
    """The policy keys of one registry."""

    def __init__(self, keys: Iterable[str]):
        self.keys = frozenset(key for key in keys if key)
        self.domains = frozenset(d for d in map(_domain, self.keys) if d)

    def __bool__(self) -> bool:
        return bool(self.keys)

    def owns(self, policy_key: Optional[str]) -> bool:
        if not policy_key:
            return False
        return policy_key in self.keys or _domain(policy_key) in self.domains

    def with_keys(self, keys: Iterable[str]) -> "PolicyScope":
        return PolicyScope(set(self.keys) | set(keys))


def seeded_policy_keys(package_dir: Path) -> set:
    """Policy keys named by the registry's own approval seed files."""
    files = []
    awe_dir = package_dir / "awe_meta_data"
    if awe_dir.is_dir():
        files += [p for p in awe_dir.rglob("*") if p.is_file()]
    meta_dir = package_dir / "meta_data"
    if meta_dir.is_dir():
        files += [p for p in meta_dir.rglob("*awe*.sql") if p.is_file()]
    keys = set()
    for path in files:
        try:
            keys.update(_POLICY_KEY.findall(path.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            _logger.warning("Cannot read approval seed %s", path)
    return keys


def paged(items: list, page: int, page_size: int) -> dict:
    """Shape ``items`` like the engine's paged task list."""
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 25))
    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 1,
    }


def task_counts(tasks: list) -> dict:
    """The three counters the staff portal's approval card reads."""
    return {
        "total": len(tasks),
        "change_request_count": sum(t.get("artifact_type") == CHANGE_REQUEST_ARTIFACT for t in tasks),
        "intake_form_count": sum(t.get("artifact_type") == INTAKE_FORM_ARTIFACT for t in tasks),
    }


class ScopedAweTasksMixin:
    """List and count only this registry's tasks.

    Put it before the platform's AWE proxy service. Task decisions, claiming
    and the per-request task list are not touched.
    """

    scope_package_dir: Path

    _seed_scope: Optional[PolicyScope] = None
    _configured_keys: tuple = ()
    _configured_at: Optional[float] = None

    # --- hooks the platform subclass fills in -------------------------------
    def _awe_helper(self):
        raise NotImplementedError

    async def _configured_policy_keys(self) -> Iterable[str]:
        return ()

    async def _call_awe(self, call):
        return await call

    # --- scope --------------------------------------------------------------
    async def _own_scope(self) -> Optional[PolicyScope]:
        """None means the seed could not be read: do not hide tasks then."""
        if self._seed_scope is None:
            self._seed_scope = PolicyScope(seeded_policy_keys(self.scope_package_dir))
            if not self._seed_scope:
                _logger.warning(
                    "No approval policy keys found under %s; task lists are not scoped",
                    self.scope_package_dir,
                )
        if not self._seed_scope:
            return None
        now = time.monotonic()
        if self._configured_at is None or now - self._configured_at > CONFIGURED_KEYS_TTL_SECONDS:
            self._configured_keys = tuple(await self._configured_policy_keys())
            self._configured_at = now
        return self._seed_scope.with_keys(self._configured_keys)

    async def _own_tasks(self, scope: PolicyScope, bearer_token: str, **filters) -> list:
        """Every task of the caller, read page by page, kept to this registry."""
        helper = self._awe_helper()
        tasks = []
        page = 1
        while page <= MAX_AWE_PAGES:
            result = await self._call_awe(helper.list_my_tasks(
                bearer_token, page=page, page_size=AWE_PAGE_SIZE, **filters))
            batch = result.get("items") or []
            tasks.extend(t for t in batch if scope.owns(t.get("policy_key")))
            if not batch or page >= (result.get("pages") or 1):
                break
            page += 1
        else:
            _logger.warning("Task listing stopped after %s pages; counts may be short", MAX_AWE_PAGES)
        return tasks

    # --- platform entry points ---------------------------------------------
    async def list_my_tasks(self, payload, *, bearer_token):
        scope = await self._own_scope()
        if scope is None:
            return await super().list_my_tasks(payload, bearer_token=bearer_token)
        if payload.policy_key:
            if not scope.owns(payload.policy_key):
                return paged([], payload.page, payload.page_size)
            # One exact key of this registry: the engine pages it correctly.
            return await super().list_my_tasks(payload, bearer_token=bearer_token)
        tasks = await self._own_tasks(
            scope, bearer_token,
            request_id=payload.request_id,
            status=payload.status,
            artifact_type=payload.artifact_type,
            search_text=payload.search_text,
        )
        return paged(tasks, payload.page, payload.page_size)

    async def my_task_stats(self, payload, *, bearer_token):
        scope = await self._own_scope()
        if scope is None:
            return await super().my_task_stats(payload, bearer_token=bearer_token)
        stats = await super().my_task_stats(payload, bearer_token=bearer_token)
        tasks = await self._own_tasks(scope, bearer_token, status=payload.status)
        return {**(stats if isinstance(stats, dict) else {}), **task_counts(tasks)}
