from collections.abc import Callable
from typing import Any

import httpx
from fastapi import Request
from openg2p_fastapi_common.errors.base_exception import BaseAppException
from openg2p_fastapi_common.errors.http_exceptions import ForbiddenError, UnauthorizedError
from starlette.middleware.base import BaseHTTPMiddleware

from iam_core.schemas import AuthPrincipal

from ..config import Settings
from ..decorators import get_required_permissions
from ..enums import RequestStateKey
from ..helpers.error_response_helper import user_auth_error_response
from ..helpers.route_helper import match_route


class ResolvePermissionMiddleware(BaseHTTPMiddleware):
    """Enforce ``@require_permissions`` using ``request.state.auth``.

    Register after ValidateAndRefreshTokenMiddleware. No token validation here.
    """

    def __init__(
        self,
        app,
        *,
        client_id: str | None = None,
        allow_by_default: bool = True,
        state_key: str | RequestStateKey = RequestStateKey.AUTH,
        permissions_state_key: str | RequestStateKey = RequestStateKey.PERMISSIONS,
        required_permissions_resolver: Callable[[Request, Any], set[str] | None] | None = None,
    ):
        super().__init__(app)
        self._client_id = client_id
        self._allow_by_default = allow_by_default
        self._state_key = str(state_key)
        self._permissions_state_key = str(permissions_state_key)
        self._required_permissions_resolver = required_permissions_resolver
        self._config = Settings.get_config(strict=False)

    async def _fetch_permissions_for_roles(self, role_mnemonics: list[str]) -> set[str]:
        """Resolve role mnemonics to permission strings via the auth provider API."""
        auth_provider_api_url = (self._config.auth_provider_api_url or "").strip()
        if not auth_provider_api_url:
            raise ForbiddenError(message="Forbidden. auth_provider_api_url is not configured.")

        if not role_mnemonics:
            return set()

        endpoint = auth_provider_api_url.rstrip("/") + "/user-access/get_permissions_for_roles"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint,
                    json={"role_mnemonics": role_mnemonics},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ForbiddenError(message="Forbidden. Unable to fetch user permissions.") from exc

        response_data = response.json() or {}
        return set(response_data.get("permissions") or [])

    async def dispatch(self, request: Request, call_next):
        # Enforce @require_permissions using roles already on request.state.auth.
        try:
            matched_route = match_route(request)
            if matched_route is None:
                return await call_next(request)

            if self._required_permissions_resolver is not None:
                permissions = self._required_permissions_resolver(request, matched_route)
                required_permissions = (
                    None if permissions is None else {str(permission) for permission in permissions}
                )
            else:
                required_permissions = get_required_permissions(getattr(matched_route, "endpoint", None))

            if required_permissions is None and self._allow_by_default:
                return await call_next(request)

            request.scope["route"] = matched_route

            client_id = (self._client_id or "").strip()
            if required_permissions and not client_id:
                raise ForbiddenError(message="Forbidden. keycloak_client_id is not configured.")

            principal = getattr(request.state, self._state_key, None)
            if not isinstance(principal, AuthPrincipal):
                raise UnauthorizedError()

            user_roles = list((principal.client_roles or {}).get(client_id, []))
            user_permissions = await self._fetch_permissions_for_roles(user_roles)

            if required_permissions and not required_permissions.issubset(user_permissions):
                raise ForbiddenError(message="Forbidden. Insufficient resource_access roles.")

            setattr(request.state, self._permissions_state_key, user_permissions)
            return await call_next(request)
        except BaseAppException as exc:
            return user_auth_error_response(request, exc)
