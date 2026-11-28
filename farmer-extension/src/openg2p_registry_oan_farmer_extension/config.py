from openg2p_registry_core.config import Settings as CoreSettings
from pydantic_settings import SettingsConfigDict

from . import __version__


class Settings(CoreSettings):
    model_config = SettingsConfigDict(
        env_prefix="registry_extensions_", env_file=".env", extra="allow"
    )

    openapi_title: str = "OpenAgriNet Farmer Registry"
    openapi_description: str = "OpenAgriNet Farmer Registry API"
    openapi_version: str = __version__
