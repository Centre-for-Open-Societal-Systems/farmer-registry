from ...models import ConnectorDefinition
from ..base import AuthContext, BaseAuthStrategy
from ..registry import register_auth


@register_auth("none")
class NoneAuth(BaseAuthStrategy):
    async def get_auth_context(self, connector: ConnectorDefinition) -> AuthContext:
        return AuthContext()
