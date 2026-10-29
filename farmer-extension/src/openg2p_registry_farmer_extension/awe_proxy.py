"""Register the registry-scoped approval task service in place of the platform's."""
import logging
from pathlib import Path

from openg2p_fastapi_common.context import component_registry, get_async_session_maker
from openg2p_registry_core.controller_services import G2PAweProxyControllerService
from openg2p_registry_core.helpers import AWEClientError, AweHelper
from sqlalchemy import text

from .awe_task_scope import ScopedAweTasksMixin

_logger = logging.getLogger("oan-awe-task-scope")


class ScopedAweProxyControllerService(ScopedAweTasksMixin, G2PAweProxyControllerService):
    scope_package_dir = Path(__file__).resolve().parent

    def _awe_helper(self):
        return AweHelper.get_component()

    async def _call_awe(self, call):
        try:
            return await call
        except AWEClientError as exc:
            raise self._wrap_awe_error(exc) from exc

    async def _configured_policy_keys(self):
        try:
            async with get_async_session_maker()() as session:
                rows = await session.execute(text(
                    "SELECT DISTINCT policy_key FROM g2p_registry_awe_policy_configurations "
                    "WHERE policy_key IS NOT NULL"))
                return [row[0] for row in rows]
        except Exception as exc:
            _logger.warning("Cannot read configured approval policies: %s", exc)
            return ()


def install():
    """Idempotent: one instance, at the platform service's position."""
    extension = next(
        (item for item in component_registry if isinstance(item, ScopedAweProxyControllerService)),
        None,
    ) or ScopedAweProxyControllerService()
    if extension in component_registry:
        component_registry.remove(extension)
    first = next(
        (index for index, item in enumerate(component_registry)
         if isinstance(item, G2PAweProxyControllerService)),
        len(component_registry),
    )
    component_registry.insert(first, extension)
