"""CRUD for ConnectorDefinition."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ConnectorDefinition
from ..schemas import ConnectorCreate, ConnectorUpdate


class ConnectorService:
    @staticmethod
    def _normalize_payload(payload: dict) -> dict:
        """Normalize optional text fields that the UI may submit as blanks."""
        if payload.get("webhook_path_slug") == "":
            payload["webhook_path_slug"] = None
        return payload

    async def list_all(self, session: AsyncSession) -> list[ConnectorDefinition]:
        result = await session.execute(
            select(ConnectorDefinition).order_by(ConnectorDefinition.name)
        )
        return list(result.scalars().all())

    async def get(self, connector_id: str, session: AsyncSession) -> ConnectorDefinition | None:
        return await session.get(ConnectorDefinition, connector_id)

    async def create(self, data: ConnectorCreate, session: AsyncSession) -> ConnectorDefinition:
        cd = ConnectorDefinition(**self._normalize_payload(data.model_dump()))
        session.add(cd)
        await session.flush()
        return cd

    async def update(
        self, connector_id: str, data: ConnectorUpdate, session: AsyncSession
    ) -> ConnectorDefinition | None:
        cd = await session.get(ConnectorDefinition, connector_id)
        if cd is None:
            return None
        for field, value in self._normalize_payload(
            data.model_dump(exclude_unset=True)
        ).items():
            setattr(cd, field, value)
        await session.flush()
        return cd

    async def delete(self, connector_id: str, session: AsyncSession) -> bool:
        cd = await session.get(ConnectorDefinition, connector_id)
        if cd is None:
            return False
        await session.delete(cd)
        await session.flush()
        return True
