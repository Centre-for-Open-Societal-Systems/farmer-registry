import asyncio
import logging

from .config import Settings

_config = Settings.get_config()

from openg2p_fastapi_common.context import dbengine
from openg2p_fastapi_common.app import Initializer as BaseInitializer
from openg2p_registry_core.app import Initializer as CoreInitializer
from sqlalchemy import text

from .register_domain import models as _oan_models

from .register_domain.services.g2p_register_domain_service_farmer import G2PRegisterDomainServiceFarmer
from .register_domain.services.g2p_register_domain_service_household import G2PRegisterDomainServiceHousehold
from .register_domain.services.g2p_register_domain_service_household_member import G2PRegisterDomainServiceHouseholdMember

_logger = logging.getLogger(_config.logging_default_logger_name)

# Parent tables must precede their dependents. Use the table-declaring Farmer models.
FARMER_REGISTERS = (
    (
        _oan_models.G2PRegisterHousehold,
        _oan_models.G2PRegisterHistoryHousehold,
        _oan_models.G2PIntakeFormHousehold,
    ),
    (
        _oan_models.G2PRegisterHouseholdMember,
        _oan_models.G2PRegisterHistoryHouseholdMember,
        _oan_models.G2PIntakeFormHouseholdMember,
    ),
    (
        _oan_models._FarmerRegister,
        _oan_models.G2PRegisterHistoryFarmer,
        _oan_models._FarmerIntakeForm,
    ),
    (
        _oan_models.G2PRegisterMembershipDetails,
        _oan_models.G2PRegisterHistoryMembershipDetails,
        _oan_models.G2PIntakeFormMembershipDetails,
    ),
    (
        _oan_models.G2PRegisterLand,
        _oan_models.G2PRegisterHistoryLand,
        _oan_models.G2PIntakeFormLand,
    ),
    (
        _oan_models.G2PRegisterFarmInputs,
        _oan_models.G2PRegisterHistoryFarmInputs,
        _oan_models.G2PIntakeFormFarmInputs,
    ),
    (
        _oan_models.G2PRegisterCrop,
        _oan_models.G2PRegisterHistoryCrop,
        _oan_models.G2PIntakeFormCrop,
    ),
    (
        _oan_models.G2PRegisterLivestock,
        _oan_models.G2PRegisterHistoryLivestock,
        _oan_models.G2PIntakeFormLivestock,
    ),
)

# OAN registers, in parent-before-child order: (register, history, intake form).
OAN_REGISTERS: list[tuple] = [
    (_oan_models.G2PRegisterFarmerPhone, _oan_models.G2PRegisterHistoryFarmerPhone, _oan_models.G2PIntakeFormFarmerPhone),
]


class Initializer(BaseInitializer):
    """Initialize the Farmer Registry on the shared registry platform."""

    def initialize(self, **kwargs):
        super().initialize()
        CoreInitializer().initialize()
        G2PRegisterDomainServiceFarmer()
        G2PRegisterDomainServiceHousehold()
        G2PRegisterDomainServiceHouseholdMember()
        from .runtime import install

        install()
        from .awe_proxy import install as install_scoped_awe_tasks

        install_scoped_awe_tasks()
        from .history_change_request_source import install as install_history_change_request_source

        install_history_change_request_source()
        from .history_without_change_request import install as install_history_without_change_request

        install_history_without_change_request()
        from .household_roster_head import install as install_household_roster_head

        install_household_roster_head()

    def migrate_database(self, args):
        async def migrate_registers():
            _logger.info("Migrating Farmer Registry tables")
            for register, history, intake in FARMER_REGISTERS:
                for model in (register, history, intake):
                    await model.create_migrate()

        asyncio.run(migrate_registers())
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
            await fill_list_summary()
            await rename_records()

        asyncio.run(migrate())


async def add_oan_columns() -> None:
    """Add the columns OAN maps on the farmer tables that an existing table lacks.

    create_all creates missing tables only, so a field added after a registry
    was first migrated (register_domain/fields.py, or core's registrant
    authentication mixin on the Farmer register) would otherwise be mapped but
    absent, and every query of that register would fail. Columns are only
    added, never changed or dropped.
    """
    from sqlalchemy import inspect as sa_inspect

    from .register_domain.fields import OAN_FIELDS

    engine = dbengine.get()
    async with engine.begin() as conn:
        for mnemonic in OAN_FIELDS:
            for prefix in ("G2PRegister", "G2PRegisterHistory", "G2PIntakeForm"):
                table = getattr(_oan_models, f"{prefix}{mnemonic}").__table__
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


# The farmer list's plot count and mobile number for farmers saved before the
# columns existed. refresh_farmer (register_domain/services/derivations.py)
# keeps them in step on every save; these are the same rules in SQL: the
# farmer's ACTIVE land rows, and the primary entry of phone_numbers, else the
# first one with a number. Only empty columns are filled.
LIST_SUMMARY_BACKFILL = (
    """UPDATE g2p_register_farmers f
       SET total_plots = (SELECT count(*) FROM g2p_register_lands l
                          WHERE l.link_internal_record_id = f.internal_record_id AND l.record_status = 'ACTIVE')
       WHERE f.total_plots IS NULL""",
    """UPDATE g2p_register_farmers f SET primary_phone_number = p.number
       FROM (SELECT f2.internal_record_id,
                    (SELECT btrim(e->>'number') FROM jsonb_array_elements(f2.phone_numbers::jsonb) WITH ORDINALITY a(e, n)
                     WHERE jsonb_typeof(e) = 'object' AND btrim(COALESCE(e->>'number', '')) <> ''
                     ORDER BY (e->'is_primary') = 'true'::jsonb IS TRUE DESC, n LIMIT 1) AS number
             FROM g2p_register_farmers f2
             WHERE f2.primary_phone_number IS NULL AND jsonb_typeof(f2.phone_numbers::jsonb) = 'array') p
       WHERE f.internal_record_id = p.internal_record_id AND p.number IS NOT NULL""",
    # registration_date: the date of the farmer's first approval in its history;
    # without history, its last approval; without either, the day it was created
    # (registration_date_of in register_domain/services/derivations.py).
    """UPDATE g2p_register_farmers f
       SET registration_date = COALESCE(
             (SELECT min(h.approved_at) FROM g2p_register_history_farmers h
              WHERE h.internal_record_id = f.internal_record_id AND h.approved_at IS NOT NULL),
             f.last_approved_at, f.created_at)::date
       WHERE f.registration_date IS NULL""",
)


async def fill_list_summary() -> None:
    """Fill total_plots, primary_phone_number and registration_date on farmers saved without them."""
    async with dbengine.get().begin() as conn:
        for statement in LIST_SUMMARY_BACKFILL:
            result = await conn.execute(text(statement))
            if result.rowcount:
                _logger.info("Filled the farmer list summary on %d rows", result.rowcount)


# Rows renamed per transaction
RENAME_BATCH = 500


async def rename_records() -> None:
    """Give the rows saved before the readable names the name they now get.

    record_name is stored when a row is saved, so every farmer and child row
    keeps the name it was saved with (the father's name missing, raw codes)
    until it is saved again. Run by the staff-api `migrate` command, this
    recomposes it for the register and history rows of the registers in
    record_names.COMPOSERS (intake forms are drafts that carry an application
    reference and are renamed when saved). A row is changed only when its stored
    name differs from the composed one, so a second run changes nothing. History
    rows are snapshots, but the name is a title and not part of the record.

    A register's search text holds its record name, so it is updated with it
    (the farmer's does not hold it). Rows are read in pages of RENAME_BATCH by
    primary key, selecting only the columns the name uses, and each page is its
    own transaction. A table that fails is logged and skipped, so a bad row
    never stops the migration.
    """
    from sqlalchemy import bindparam, select, update
    from sqlalchemy import inspect as sa_inspect

    from .register_domain.record_names import COMPOSERS, FIELDS, compose, renamed_search_text

    engine = dbengine.get()
    tables = [
        (mnemonic, getattr(_oan_models, f"{prefix}{mnemonic}").__table__)
        for mnemonic in COMPOSERS
        for prefix in ("G2PRegister", "G2PRegisterHistory")
    ]
    for mnemonic, table in tables:
        try:
            async with engine.connect() as conn:
                exists = await conn.run_sync(lambda sconn, name=table.name: sa_inspect(sconn).has_table(name))
            keys = list(table.primary_key.columns)
            if not exists or "record_name" not in table.c or len(keys) != 1:
                continue
            key = keys[0]
            uses_search_text = "search_text" in table.c and mnemonic != "Farmer"
            columns = [key, table.c.record_name, *(table.c[f] for f in FIELDS[mnemonic] if f in table.c)]
            if uses_search_text:
                columns.append(table.c.search_text)
            statement = update(table).where(key == bindparam("pk")).values(record_name=bindparam("new_name"))
            if uses_search_text:
                statement = statement.values(search_text=bindparam("new_search_text"))
            last, renamed = None, 0
            while True:
                query = select(*columns).order_by(key).limit(RENAME_BATCH)
                if last is not None:
                    query = query.where(key > last)
                async with engine.begin() as conn:
                    rows = (await conn.execute(query)).mappings().all()
                    if not rows:
                        break
                    last = rows[-1][key.name]
                    changes = []
                    for row in rows:
                        name = compose(mnemonic, dict(row))
                        if name and name != row["record_name"]:
                            change = {"pk": row[key.name], "new_name": name}
                            if uses_search_text:
                                change["new_search_text"] = renamed_search_text(
                                    row["search_text"], row["record_name"], name)
                            changes.append(change)
                    if changes:
                        await conn.execute(statement, changes)
                        renamed += len(changes)
            if renamed:
                _logger.info("Renamed %d rows of %s", renamed, table.name)
        except Exception as error:
            _logger.warning("Could not rename the rows of %s: %s", table.name, error)


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
