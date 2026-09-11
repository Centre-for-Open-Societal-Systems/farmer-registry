# ruff: noqa: E402
import asyncio
import logging

from .config import Settings

_config = Settings.get_config()

from openg2p_fastapi_common.app import Initializer as BaseInitializer
from openg2p_fastapi_common.context import dbengine
from openg2p_registry_core.app import Initializer as CoreInitializer
from sqlalchemy import text

from .register_domain.models import (
    G2PRegisterFarmer, G2PRegisterHistoryFarmer,
    G2PRegisterFarmerPhone, G2PRegisterHistoryFarmerPhone,
    G2PRegisterHousehold, G2PRegisterHistoryHousehold,
    G2PRegisterHouseholdMember, G2PRegisterHistoryHouseholdMember,
    G2PRegisterCrop, G2PRegisterHistoryCrop,
    G2PRegisterLand, G2PRegisterHistoryLand,
    G2PRegisterFarmInputs, G2PRegisterHistoryFarmInputs,
    G2PRegisterLivestock, G2PRegisterHistoryLivestock,
    G2PRegisterMembershipDetails, G2PRegisterHistoryMembershipDetails,
    G2PRegisterRegId, G2PRegisterHistoryRegId,
    G2PRegisterConsentRequest, G2PRegisterHistoryConsentRequest,
    G2PRegisterConsentReceipt, G2PRegisterHistoryConsentReceipt,
    G2PIntakeFormHousehold, G2PIntakeFormFarmer, G2PIntakeFormFarmerPhone, G2PIntakeFormHouseholdMember,
    G2PIntakeFormCrop, G2PIntakeFormLand, G2PIntakeFormFarmInputs,
    G2PIntakeFormLivestock, G2PIntakeFormMembershipDetails, G2PIntakeFormRegId,
    G2PIntakeFormConsentRequest, G2PIntakeFormConsentReceipt,
)
from .register_domain.factory import G2PRegisterDomainFactory
from .register_domain.services import (
    G2PRegisterDomainServiceFarmer,
    G2PRegisterDomainServiceHousehold,
    install_record_image_url_resolution,
)

_logger = logging.getLogger(_config.logging_default_logger_name)


class Initializer(BaseInitializer):
    def initialize(self, **kwargs):
        super().initialize()
        CoreInitializer().initialize()

        # Intake reads return record_image_document_id but never the presigned
        # record_image_url the register-side reads add, so a photo captured at
        # intake has nothing to render on the approval screen. Patches the
        # platform class rather than registering a subclass — see the function
        # for why a subclass cannot win the component lookup.
        install_record_image_url_resolution()

        G2PRegisterDomainFactory()
        G2PRegisterDomainServiceFarmer()
        G2PRegisterDomainServiceHousehold()

    async def fastapi_app_startup(self, app):
        # The explicit CLI `migrate` step is a separate invocation from
        # serving traffic (see the image's CMD: "migrate; gunicorn ...").
        # Deployments that override the container command/args can skip that
        # step silently — the server then starts against a schema missing
        # every extension column added here, failing every query that
        # touches one (e.g. "column g2p_register_farmers.state does not
        # exist"). Re-running these ALTER TABLE ADD COLUMN IF NOT EXISTS /
        # idempotent UPDATE statements on every startup, not just on an
        # explicit `migrate` invocation, makes the schema self-healing
        # regardless of what the deployment's command ends up being.
        #
        # This runs from fastapi_app_startup — awaited inside the ASGI
        # lifespan's own event loop — rather than from initialize() via
        # asyncio.run(). initialize() runs synchronously at import time and
        # can fire more than once per process; asyncio.run() opens and tears
        # down a fresh event loop on every call, so a second call reuses a
        # dbengine/connection pool whose asyncpg connections are still bound
        # to the first (now-closed) loop, raising "attached to a different
        # loop". fastapi_app_startup runs exactly once per worker, inside
        # the loop that will actually serve requests, so there's no
        # cross-loop reuse.
        await self._migrate_extension_tables()

    def migrate_database(self, args):
        asyncio.run(self._migrate_extension_tables())

    async def _migrate_extension_tables(self):
        _logger.info("Migrating extensions database")

        await G2PRegisterHousehold.create_migrate()
        await G2PRegisterHistoryHousehold.create_migrate()
        await G2PIntakeFormHousehold.create_migrate()

        await G2PRegisterHouseholdMember.create_migrate()
        await G2PRegisterHistoryHouseholdMember.create_migrate()
        await G2PIntakeFormHouseholdMember.create_migrate()

        await G2PRegisterFarmer.create_migrate()
        await G2PRegisterHistoryFarmer.create_migrate()
        await G2PIntakeFormFarmer.create_migrate()

        await G2PRegisterFarmerPhone.create_migrate()
        await G2PRegisterHistoryFarmerPhone.create_migrate()
        await G2PIntakeFormFarmerPhone.create_migrate()

        # Land must exist before the land_extension_columns ALTER TABLE
        # block below (it targets g2p_register_lands directly) — moved
        # up from its previous spot alongside the other post-Land
        # create_migrate() calls, which ran after this ALTER block and
        # left it erroring "relation g2p_register_lands does not exist"
        # on any fresh database.
        await G2PRegisterLand.create_migrate()
        await G2PRegisterHistoryLand.create_migrate()
        await G2PIntakeFormLand.create_migrate()

        # SQLAlchemy create_all() creates missing tables but intentionally
        # does not add columns to tables that already exist. Keep extension
        # upgrades idempotent for existing Registry installations.
        async with dbengine.get().begin() as conn:
            extension_columns = {
                "is_household_head": (
                    "g2p_register_farmers",
                    "g2p_register_history_farmers",
                    "g2p_intake_form_farmers",
                ),
                "father_included": (
                    "g2p_register_households",
                    "g2p_register_history_households",
                    "g2p_intake_form_households",
                ),
                "mother_included": (
                    "g2p_register_households",
                    "g2p_register_history_households",
                    "g2p_intake_form_households",
                ),
            }
            for column_name, table_names in extension_columns.items():
                for table_name in table_names:
                    await conn.execute(
                        text(
                            f'ALTER TABLE "public"."{table_name}" '
                            f'ADD COLUMN IF NOT EXISTS "{column_name}" BOOLEAN'
                        )
                    )

            for table_name in (
                "g2p_register_farmers",
                "g2p_register_history_farmers",
                "g2p_intake_form_farmers",
            ):
                # Installations created before the Ethiopic column became a
                # string still have it as DATE, which cannot hold Pagumen
                # (month 13) at all. Convert in place, rendering any existing
                # value with to_char so the stored text keeps the same day.
                # Guarded on the current type so the ALTER is a no-op on the
                # second and every later boot.
                await conn.execute(
                    text(
                        f'ALTER TABLE "public"."{table_name}" '
                        'ADD COLUMN IF NOT EXISTS "birth_date_ec" VARCHAR'
                    )
                )
                await conn.execute(
                    text(
                        f"""
                        DO $$
                        BEGIN
                            IF EXISTS (
                                SELECT 1 FROM information_schema.columns
                                 WHERE table_schema = 'public'
                                   AND table_name = '{table_name}'
                                   AND column_name = 'birth_date_ec'
                                   AND data_type = 'date'
                            ) THEN
                                ALTER TABLE "public"."{table_name}"
                                ALTER COLUMN "birth_date_ec" TYPE VARCHAR
                                USING to_char("birth_date_ec", 'YYYY-MM-DD');
                            END IF;
                        END $$;
                        """
                    )
                )
                await conn.execute(
                    text(
                        f'ALTER TABLE "public"."{table_name}" '
                        'ADD COLUMN IF NOT EXISTS "state" VARCHAR'
                    )
                )
                await conn.execute(
                    text(
                        f'ALTER TABLE "public"."{table_name}" '
                        'ADD COLUMN IF NOT EXISTS "import_source" VARCHAR'
                    )
                )
                # Father's name triple (see models/farmer.py). Declared on the
                # model, so create_all() covers fresh databases; this covers the
                # ones that already existed.
                for father_column in (
                    "father_first_name", "father_middle_name", "father_last_name",
                ):
                    await conn.execute(
                        text(
                            f'ALTER TABLE "public"."{table_name}" '
                            f'ADD COLUMN IF NOT EXISTS "{father_column}" VARCHAR'
                        )
                    )
                # region_name/zone_name/woreda_name/kebele_name were declared
                # on the model (flattened out of geo_code_hierarchy_json) but
                # never had a matching ALTER TABLE entry here — the same
                # missing-column bug class already hit "state" in production.
                # woreda_level_value_id is new: the raw geo id (not just the
                # display name) so the Land table's kebele dropdown can filter
                # by this farmer's own woreda.
                for geo_column in (
                    "region_name", "zone_name", "woreda_name", "kebele_name",
                    "woreda_level_value_id",
                ):
                    await conn.execute(
                        text(
                            f'ALTER TABLE "public"."{table_name}" '
                            f'ADD COLUMN IF NOT EXISTS "{geo_column}" VARCHAR'
                        )
                    )

                # Older section-by-section intake saves cleared these list
                # projections even though the selected location and hierarchy
                # survived. Recover only missing projections from each row's
                # own snapshot, including intake and history twins. No location
                # is invented for farmers who never supplied one.
                for level, aliases in (
                    ("region", "'region'"),
                    ("zone", "'zone', 'district'"),
                    ("woreda", "'woreda', 'ward'"),
                    ("kebele", "'kebele', 'village'"),
                ):
                    await conn.execute(text(f"""
                        UPDATE public.{table_name} AS farmer
                        SET {level}_name = (
                            SELECT COALESCE(
                                NULLIF(entry->>'level_value_display_name', ''),
                                NULLIF(entry->>'level_value_name', ''),
                                NULLIF(entry->>'display_name', ''),
                                NULLIF(entry->>'level_value_mnemonic', '')
                            )
                            FROM jsonb_array_elements(
                                farmer.geo_code_hierarchy_json->'hierarchy'
                            ) AS entry
                            WHERE lower(entry->>'level_mnemonic') IN ({aliases})
                            LIMIT 1
                        )
                        WHERE NULLIF(farmer.{level}_name, '') IS NULL
                          AND jsonb_typeof(
                              farmer.geo_code_hierarchy_json->'hierarchy'
                          ) = 'array'
                    """))
                await conn.execute(text(f"""
                    UPDATE public.{table_name} AS farmer
                    SET woreda_level_value_id = (
                        SELECT entry->>'level_value_id'
                        FROM jsonb_array_elements(
                            farmer.geo_code_hierarchy_json->'hierarchy'
                        ) AS entry
                        WHERE lower(entry->>'level_mnemonic') IN ('woreda', 'ward')
                        LIMIT 1
                    )
                    WHERE NULLIF(farmer.woreda_level_value_id, '') IS NULL
                      AND jsonb_typeof(
                          farmer.geo_code_hierarchy_json->'hierarchy'
                      ) = 'array'
                """))

            # A row only enters the live register after approval. Project
            # that workflow fact onto existing Farmer rows, and recover
            # their source from the newest history version where possible.
            await conn.execute(
                text(
                    """
                    UPDATE public.g2p_register_farmers
                    SET state = 'APPROVED'
                    WHERE state IS NULL
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    WITH latest_source AS (
                        SELECT DISTINCT ON (internal_record_id)
                            internal_record_id,
                            change_request_source
                        FROM public.g2p_register_history_farmers
                        WHERE change_request_source IN (
                            'INTAKE_FORM',
                            'PARTNER',
                            'STAFF_PORTAL',
                            'BENEFICIARY_PORTAL',
                            'AGENT_PORTAL'
                        )
                        ORDER BY
                            internal_record_id,
                            approved_at DESC NULLS LAST,
                            created_at DESC NULLS LAST
                    )
                    UPDATE public.g2p_register_farmers AS farmer
                    SET import_source = latest_source.change_request_source
                    FROM latest_source
                    WHERE farmer.internal_record_id =
                          latest_source.internal_record_id
                      AND farmer.import_source IS NULL
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    UPDATE public.g2p_register_farmers
                    SET import_source = 'IMPORT_FILE'
                    WHERE import_source IS NULL
                    """
                )
            )

            # Until the father's name became its own first/middle/last
            # triple, the intake form's mandatory second name was "Middle
            # Name" -- and, Ethiopian naming having no middle name of its
            # own, that slot held the father's name (validation_rules
            # REQUIRED_NAME_FIELDS was first_name + middle_name). Move it
            # across for every record a person typed in, so those farmers
            # satisfy the new required father_first_name without staff
            # re-entering it, and so "Middle Name" stops displaying a
            # father as the farmer's own name.
            #
            # Only form-entered records: for imports and partner feeds the
            # source system decides what middle_name means, and the seed's
            # own sample pack fills it with genuine middle names. Rows that
            # already carry a father_first_name are left alone, which is
            # what makes this safe to re-run on every boot. Intake drafts
            # have no import_source -- they are form-entered by definition.
            for table_name, source_filter in (
                (
                    "g2p_register_farmers",
                    "AND upper(import_source) IN "
                    "('INTAKE_FORM', 'STAFF_PORTAL', 'AGENT_PORTAL', "
                    "'BENEFICIARY_PORTAL')",
                ),
                ("g2p_intake_form_farmers", ""),
            ):
                moved = await conn.execute(
                    text(
                        f"""
                        UPDATE public.{table_name}
                        SET father_first_name = middle_name,
                            middle_name = NULL
                        WHERE NULLIF(father_first_name, '') IS NULL
                          AND NULLIF(middle_name, '') IS NOT NULL
                          {source_filter}
                        """
                    )
                )
                if moved.rowcount:
                    _logger.info(
                        "Moved middle_name into father_first_name for %s "
                        "form-entered rows of %s",
                        moved.rowcount,
                        table_name,
                    )

            # Existing seed/import data often contains a Gregorian birth
            # date but leaves the legacy estimated_age field empty. Keep
            # the stored Age available to the metadata-driven UI.
            await conn.execute(
                text(
                    """
                    UPDATE public.g2p_register_farmers
                    SET estimated_age = extract(
                        year FROM age(current_date, birth_date)
                    )::integer
                    WHERE birth_date IS NOT NULL
                      AND estimated_age IS NULL
                    """
                )
            )

            land_extension_columns = {
                "area_in_hectare": "NUMERIC(16, 6)",
                "land_kebele": "VARCHAR",
                "certificate_provided": "BOOLEAN",
            }
            for column_name, column_type in land_extension_columns.items():
                for table_name in (
                    "g2p_register_lands",
                    "g2p_register_history_lands",
                    "g2p_intake_form_lands",
                ):
                    await conn.execute(
                        text(
                            f'ALTER TABLE "public"."{table_name}" '
                            f'ADD COLUMN IF NOT EXISTS "{column_name}" {column_type}'
                        )
                    )

            await conn.execute(
                text(
                    """
                    UPDATE public.g2p_register_lands
                    SET area_in_hectare = land_size * CASE unit
                        WHEN 'HECTARE' THEN 1.0
                        WHEN 'ACRE' THEN 0.404686
                        WHEN 'SQUARE_METER' THEN 0.0001
                        WHEN 'SQUARE_KM' THEN 100.0
                        WHEN 'SQUARE_FOOT' THEN 0.0000092903
                        WHEN 'SQUARE_YARD' THEN 0.0000836127
                        ELSE 1.0
                    END
                    WHERE area_in_hectare IS NULL
                      AND land_size IS NOT NULL
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    UPDATE public.g2p_register_lands
                    SET certificate_provided = (
                        nullif(btrim(certificate_storage_id), '') IS NOT NULL
                    )
                    WHERE certificate_provided IS NULL
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    WITH kebele_values AS (
                        SELECT
                            land.internal_record_id,
                            (
                                SELECT initcap(replace(replace(
                                    item->>'level_value_mnemonic', '_', ' '
                                ), '-', ' '))
                                FROM jsonb_array_elements(
                                    coalesce(
                                        land.geo_code_hierarchy_json::jsonb
                                            ->'hierarchy',
                                        '[]'::jsonb
                                    )
                                ) AS item
                                WHERE lower(item->>'level_mnemonic')
                                    IN ('kebele', 'village')
                                ORDER BY CASE
                                    WHEN lower(item->>'level_mnemonic') = 'kebele'
                                    THEN 0 ELSE 1
                                END
                                LIMIT 1
                            ) AS display_name
                        FROM public.g2p_register_lands AS land
                        WHERE land.land_kebele IS NULL
                    )
                    UPDATE public.g2p_register_lands AS land
                    SET land_kebele = kebele_values.display_name
                    FROM kebele_values
                    WHERE kebele_values.internal_record_id
                        = land.internal_record_id
                      AND kebele_values.display_name IS NOT NULL
                    """
                )
            )

            # PhoneTypeEnum was narrowed to PRIMARY/SECONDARY/OTHER to match
            # the ATI Odoo source (g2p_ati/models/phone_number.py), which
            # only ever offered those three. Existing rows still carry the
            # old MOBILE/PERSONAL/HOME/WORK values and a country_code
            # column matching that source's country_id is new.
            for table_name in (
                "g2p_register_farmer_phones",
                "g2p_register_history_farmer_phones",
                "g2p_intake_form_farmer_phones",
            ):
                await conn.execute(
                    text(
                        f'ALTER TABLE "public"."{table_name}" '
                        'ADD COLUMN IF NOT EXISTS "country_code" VARCHAR'
                    )
                )
            await conn.execute(
                text(
                    """
                    UPDATE public.g2p_register_farmer_phones
                    SET phone_type = CASE WHEN is_primary THEN 'PRIMARY' ELSE 'SECONDARY' END
                    WHERE phone_type NOT IN ('PRIMARY', 'SECONDARY', 'OTHER')
                    """
                )
            )

            # Convert the legacy Farmer.phone_numbers JSON projection into
            # proper child records. Deterministic IDs and ON CONFLICT make
            # this safe to run on every upgrade or container restart.
            await conn.execute(
                text(
                    """
                    WITH expanded AS (
                        SELECT
                            f.*,
                            phone.item,
                            phone.ordinality,
                            row_number() OVER (
                                PARTITION BY f.internal_record_id
                                ORDER BY
                                    CASE
                                        WHEN lower(coalesce(phone.item->>'is_primary', 'false'))
                                            IN ('true', '1', 'yes') THEN 0
                                        ELSE 1
                                    END,
                                    phone.ordinality
                            ) AS primary_rank
                        FROM public.g2p_register_farmers AS f
                        CROSS JOIN LATERAL jsonb_array_elements(
                            -- New farmers may store JSON null, which COALESCE
                            -- does not treat as SQL NULL. Expand arrays only.
                            CASE WHEN jsonb_typeof(f.phone_numbers) = 'array'
                                 THEN f.phone_numbers ELSE '[]'::jsonb END
                        ) WITH ORDINALITY AS phone(item, ordinality)
                        WHERE nullif(btrim(phone.item->>'number'), '') IS NOT NULL
                    )
                    INSERT INTO public.g2p_register_farmer_phones (
                        internal_record_id,
                        functional_record_id,
                        link_internal_record_id,
                        link_foundational_id,
                        record_name,
                        record_image_document_id,
                        created_by,
                        created_at,
                        last_approved_at,
                        last_approved_by,
                        search_text,
                        record_status,
                        record_status_reason,
                        phone_type,
                        phone_number,
                        is_primary
                    )
                    SELECT
                        expanded.internal_record_id || '-phone-' || expanded.ordinality,
                        NULL,
                        expanded.internal_record_id,
                        expanded.foundational_id,
                        btrim(expanded.item->>'number'),
                        NULL,
                        expanded.created_by,
                        expanded.created_at,
                        expanded.last_approved_at,
                        expanded.last_approved_by,
                        concat_ws(
                            ' ',
                            upper(coalesce(nullif(expanded.item->>'type', ''), 'OTHER')),
                            btrim(expanded.item->>'number')
                        ),
                        'ACTIVE',
                        NULL,
                        CASE
                            WHEN expanded.primary_rank = 1
                                AND lower(coalesce(expanded.item->>'is_primary', 'false'))
                                    IN ('true', '1', 'yes')
                            THEN 'PRIMARY'
                            WHEN upper(coalesce(nullif(expanded.item->>'type', ''), 'OTHER')) = 'OTHER'
                            THEN 'OTHER'
                            ELSE 'SECONDARY'
                        END,
                        btrim(expanded.item->>'number'),
                        expanded.primary_rank = 1
                            AND lower(coalesce(expanded.item->>'is_primary', 'false'))
                                IN ('true', '1', 'yes')
                    FROM expanded
                    ON CONFLICT (internal_record_id) DO NOTHING
                    """
                )
            )

            # Preserve known head-of-household information from existing
            # linked Household records without guessing for unlinked rows.
            await conn.execute(
                text(
                    """
                    WITH ranked_linked_farmers AS (
                        SELECT
                            farmer.internal_record_id,
                            household.household_head,
                            lower(btrim(farmer.record_name)) =
                                lower(btrim(household.household_head))
                                AS name_matches_head,
                            row_number() OVER (
                                PARTITION BY household.internal_record_id
                                ORDER BY
                                    CASE
                                        WHEN lower(btrim(farmer.record_name)) =
                                            lower(btrim(household.household_head))
                                        THEN 0
                                        ELSE 1
                                    END,
                                    farmer.created_at,
                                    farmer.internal_record_id
                            ) AS household_rank
                        FROM public.g2p_register_farmers AS farmer
                        JOIN public.g2p_register_households AS household
                          ON household.internal_record_id =
                             farmer.link_internal_record_id
                    )
                    UPDATE public.g2p_register_farmers AS farmer
                    SET is_household_head = (
                        ranked.household_head IS NOT NULL
                        AND ranked.name_matches_head
                        AND ranked.household_rank = 1
                    )
                    FROM ranked_linked_farmers AS ranked
                    WHERE ranked.internal_record_id = farmer.internal_record_id
                    """
                )
            )

        await G2PRegisterMembershipDetails.create_migrate()
        await G2PRegisterHistoryMembershipDetails.create_migrate()
        await G2PIntakeFormMembershipDetails.create_migrate()

        await G2PRegisterFarmInputs.create_migrate()
        await G2PRegisterHistoryFarmInputs.create_migrate()
        await G2PIntakeFormFarmInputs.create_migrate()

        await G2PRegisterCrop.create_migrate()
        await G2PRegisterHistoryCrop.create_migrate()
        await G2PIntakeFormCrop.create_migrate()

        await G2PRegisterLivestock.create_migrate()
        await G2PRegisterHistoryLivestock.create_migrate()
        await G2PIntakeFormLivestock.create_migrate()

        await G2PRegisterRegId.create_migrate()
        await G2PRegisterHistoryRegId.create_migrate()
        await G2PIntakeFormRegId.create_migrate()

        await G2PRegisterConsentRequest.create_migrate()
        await G2PRegisterHistoryConsentRequest.create_migrate()
        await G2PIntakeFormConsentRequest.create_migrate()

        await G2PRegisterConsentReceipt.create_migrate()
        await G2PRegisterHistoryConsentReceipt.create_migrate()
        await G2PIntakeFormConsentReceipt.create_migrate()

