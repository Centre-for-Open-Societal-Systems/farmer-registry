"""The pinned platform's registrant authentication service calls
``get_async_session_maker`` without importing it, so every call of core's
``authenticate_registrant`` (the id-authentication widget on the farmer's
record) fails with a NameError. Upstream's source imports it; until the pinned
images do, give the module the name it uses. A no-op once the import is there.
"""

from openg2p_registry_core.services import (
    g2p_registrant_authentication_service as _core,
)


def install_registrant_auth_compat() -> None:
    if not hasattr(_core, "get_async_session_maker"):
        from openg2p_fastapi_common.context import get_async_session_maker

        _core.get_async_session_maker = get_async_session_maker
