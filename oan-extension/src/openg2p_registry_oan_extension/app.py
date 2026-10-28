import asyncio
import logging

from .config import Settings

_config = Settings.get_config()

from openg2p_fastapi_common.context import dbengine
from openg2p_registry_farmer_extension.app import Initializer as FarmerInitializer
from sqlalchemy import text

# The farmer initializer migrates its mapped classes directly, so the OAN
# columns must be appended to them before any migration runs.
from .register_domain import models as _oan_models

_logger = logging.getLogger(_config.logging_default_logger_name)

# OAN registers, in parent-before-child order: (register, history, intake form).
OAN_REGISTERS: list[tuple] = [
    (_oan_models.G2PRegisterFarmerPhone, _oan_models.G2PRegisterHistoryFarmerPhone, _oan_models.G2PIntakeFormFarmerPhone),
]


class Initializer(FarmerInitializer):
    """The farmer extension's initializer, then OAN's registers."""

    def initialize(self, **kwargs):
        super().initialize(**kwargs)
        from .runtime import install

        install()

    def migrate_database(self, args):
        super().migrate_database(args)
        # The farmer migration ran in its own event loop, which is closed now, and
        # the pooled connections belong to it. Drop them without closing them.
        dbengine.get().sync_engine.dispose(close=False)

        async def migrate():
            _logger.info("Migrating OAN registers")
            for classes in OAN_REGISTERS:
                for cls in classes:
                    await cls.create_migrate()
            await add_oan_columns()
            from .schema_compat import migrate_existing_schema

            await migrate_existing_schema(dbengine.get())
            await fill_derived_columns()

        asyncio.run(migrate())


async def add_oan_columns() -> None:
    """Add the columns OAN maps on the farmer tables that an existing table lacks.

    create_all creates missing tables only, so a field added after a registry
    was first migrated (register_domain/fields.py, or core's registrant
    authentication mixin on the Farmer register) would otherwise be mapped but
    absent, and every query of that register would fail. Columns are only
    added, never changed or dropped.
    """
    from openg2p_registry_farmer_extension.register_domain import (
        models as farmer_models,
    )
    from sqlalchemy import inspect as sa_inspect

    from .register_domain.fields import OAN_FIELDS

    engine = dbengine.get()
    async with engine.begin() as conn:
        for mnemonic in OAN_FIELDS:
            for prefix in ("G2PRegister", "G2PRegisterHistory", "G2PIntakeForm"):
                table = getattr(farmer_models, f"{prefix}{mnemonic}").__table__
                present = await conn.run_sync(
                    lambda sconn, name=table.name: {c["name"] for c in sa_inspect(sconn).get_columns(name)}
                    if sa_inspect(sconn).has_table(name) else None)
                if present is None:
                    continue
                for column in table.c:
                    if column.name not in present:
                        _logger.info("Adding column %s.%s", table.name, column.name)
                        await conn.execute(text(
                            f'ALTER TABLE "{table.name}" ADD COLUMN IF NOT EXISTS "{column.name}" {column_ddl(column, engine.dialect)}'))


async def fill_derived_columns() -> None:
    """Fill search_text and record_name on farmer rows saved without them.

    Rows saved through the OAN subclasses before their listeners were
    registered (register_domain/models) have both columns NULL, which hides
    them from the register list. Only rows with a NULL search_text are
    touched, so this is a no-op once they are filled.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from .register_domain.models import _populate_derived_columns

    async with AsyncSession(dbengine.get(), expire_on_commit=False) as session:
        for cls in (_oan_models.G2PRegisterFarmer, _oan_models.G2PIntakeFormFarmer):
            rows = (await session.execute(select(cls).where(cls.search_text.is_(None)))).scalars().all()
            for row in rows:
                _populate_derived_columns(None, None, row)
            if rows:
                _logger.info("Filled search_text on %d %s rows", len(rows), cls.__tablename__)
        await session.commit()


def column_ddl(column, dialect) -> str:
    """The type, and the NOT NULL DEFAULT a non-nullable column with a scalar
    default needs so the rows already in the table get a value."""
    ddl = column.type.compile(dialect=dialect)
    default = column.default
    if not column.nullable and default is not None and getattr(default, "is_scalar", False):
        value = default.arg
        literal = "true" if value is True else "false" if value is False else repr(value)
        ddl += f" NOT NULL DEFAULT {literal}"
    return ddl
