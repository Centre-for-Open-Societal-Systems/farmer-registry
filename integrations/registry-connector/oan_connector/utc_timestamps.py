"""Match upstream's UTC poll clock to its timestamp-without-time-zone column."""
from datetime import timezone

from sqlalchemy import event

from openg2p_connector_service.models import ConnectorDefinition


def normalize_poll_time(target, value, oldvalue, initiator):
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


# Keep the existing schema and stored UTC values compatible. SQLAlchemy applies
# this before asyncpg binds the aware value assigned by upstream's poll worker.
event.listen(ConnectorDefinition.last_poll_at, "set", normalize_poll_time, retval=True)
