"""Import all strategies so their @register_auth decorators fire."""

from .none_auth import NoneAuth  # noqa: F401
from .static_bearer import StaticBearerAuth  # noqa: F401
from .odk_session import OdkSessionAuth  # noqa: F401
from .oauth2_client_credentials import OAuth2ClientCredentialsAuth  # noqa: F401
from .oauth2_password import OAuth2PasswordAuth  # noqa: F401
