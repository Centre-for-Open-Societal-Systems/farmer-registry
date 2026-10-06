from .base import AuthContext, BaseAuthStrategy
from .registry import auth_registry, register_auth, get_auth_strategy

# Import the strategies subpackage so each @register_auth decorator runs whenever
# anything imports `.auth` (API, Celery worker, scripts). Without this, Celery
# workers polled connectors and failed with "Unknown auth strategy: 'odk_session'".
from . import strategies as _strategies  # noqa: F401

__all__ = [
    "AuthContext",
    "BaseAuthStrategy",
    "auth_registry",
    "register_auth",
    "get_auth_strategy",
]
