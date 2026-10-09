from ...models import ConnectorDefinition
from ..base import AuthContext, BaseAuthStrategy
from ..registry import register_auth


@register_auth("static_bearer")
class StaticBearerAuth(BaseAuthStrategy):
    async def get_auth_context(self, connector: ConnectorDefinition) -> AuthContext:
        secrets = connector.get_auth_secrets()
        token = secrets.get("token", "")
        if not token:
            raise ValueError(
                f"Connector {connector.connector_id}: auth_type=static_bearer "
                "but auth_secret_json.token is empty"
            )
        return AuthContext(headers={"Authorization": f"Bearer {token}"})
