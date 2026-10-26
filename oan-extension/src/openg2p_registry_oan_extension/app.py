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

    async def fastapi_app_startup(self, app):
        await super().fastapi_app_startup(app)
        # The staff API builds its FastAPI app after this initializer, so the
        # route is added at startup, to that app. Only the staff API has core's
        # registrant authentication controller.
        from importlib.util import find_spec

        if find_spec("openg2p_registry_staff_api"):
            from .controllers import OANIdentityVerificationController

            OANIdentityVerificationController().post_init()

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

        asyncio.run(migrate())


async def add_oan_columns() -> None:
    """Add the OAN fields (register_domain/fields.py) that an existing farmer table lacks.

    create_all creates missing tables only, so a field added after a registry
    was first migrated would otherwise be mapped but absent, and every query
    of that register would fail. Columns are only added, never changed or
    dropped.
    """
    from openg2p_registry_farmer_extension.register_domain import (
        models as farmer_models,
    )
    from sqlalchemy import inspect as sa_inspect

    from .register_domain.fields import OAN_FIELDS

    engine = dbengine.get()
    async with engine.begin() as conn:
        for mnemonic, fields in OAN_FIELDS.items():
            for prefix in ("G2PRegister", "G2PRegisterHistory", "G2PIntakeForm"):
                table = getattr(farmer_models, f"{prefix}{mnemonic}").__table__
                present = await conn.run_sync(
                    lambda sconn, name=table.name: {c["name"] for c in sa_inspect(sconn).get_columns(name)}
                    if sa_inspect(sconn).has_table(name) else None)
                if present is None:
                    continue
                for name in fields:
                    if name not in present:
                        column_type = table.c[name].type.compile(dialect=engine.dialect)
                        _logger.info("Adding column %s.%s", table.name, name)
                        await conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN IF NOT EXISTS "{name}" {column_type}'))
