import logging
from datetime import date

from openg2p_registry_core.models import G2PRegisterChangeRequest
from openg2p_registry_core.services import G2PRegisterDomainService
from openg2p_fastapi_common.context import dbengine
from sqlalchemy import select, text, update

from .domain_validation_utils import (
    as_bool,
    as_int,
    is_embedded_file,
    parse_date,
    upload_embedded_file,
    validation_error,
)
from .ethiopian_calendar import (
    ethiopic_to_gregorian,
    format_ethiopic,
    gregorian_to_ethiopic_string,
    parse_ethiopic,
)
from .validation_rules import (
    NAME_FIELDS,
    NAME_MAX_LENGTH,
    NAME_PATTERN,
    REQUIRED_NAME_FIELDS,
    is_interactive,
    matches,
)

_logger = logging.getLogger("g2p-register-domain-service")

FARMER_REGISTER_ID = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"
HOUSEHOLD_REGISTER_ID = "9055ab43-c85d-4833-bd00-ca657bb72644"


class G2PRegisterDomainServiceFarmer(G2PRegisterDomainService):
    _IMPORT_SOURCES = {
        "INTAKE_FORM",
        "IMPORT_FILE",
        "PARTNER",
        "STAFF_PORTAL",
        "BENEFICIARY_PORTAL",
        "AGENT_PORTAL",
        "VERIFIABLE_CREDENTIAL",
    }

    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._normalize_booleans(record)
            await self._persist_embedded_profile_photo(record)
            self._validate_names(record)
            self._validate_birth_date(record)
            self._sync_ethiopian_birth_date(record)
            self._populate_age_from_birth_date(record)
            self._validate_estimated_age(record)
            await self._sync_flattened_geo_names(record)

    @staticmethod
    def _normalize_booleans(record: dict) -> None:
        # Select/dropdown-backed booleans (e.g. "Are You a Household Head?")
        # submit the string 'true'/'false' rather than a real bool, which
        # asyncpg rejects outright ("Not a boolean value: 'true'"). A control
        # left untouched submits '' instead, which fails the same way.
        # as_bool() normalizes both; anything already a real bool passes
        # through unchanged.
        #
        # '' maps to None, not False: every one of these is optional, so an
        # unanswered Yes/No is "not asked", which is distinct from "No" and
        # must stay NULL in the (nullable) columns -- the same rule the
        # household service applies to its flags. Readers only test
        # truthiness, so None and False behave alike downstream.
        for field in ("has_personal_phone", "disabled", "is_psnp_user", "is_household_head"):
            if not isinstance(record.get(field), bool):
                record[field] = as_bool(record.get(field))

    @staticmethod
    async def _persist_embedded_profile_photo(record: dict) -> None:
        """A freshly-picked photo arrives as an embedded base64 blob in one of
        two places, depending on which widget captured it:

        - The header-section widget's picker writes it into record_image_url
          (a server-computed, read-only field — it only exists as an
          auto-added presigned URL on read, per
          G2PRegisterService/G2PRegisterHierarchicalService, and isn't a real
          column). Left as-is, that embedded file is silently dropped on save.
          Both the register detail view (zz_farmer_header_layout.sql) and the
          intake form's photo section (zz_farmer_photo_section.sql) go this
          way — the intake section reuses that same widget for its picker.
        - Any 'file' widget bound straight to record_image_document_id writes
          the blob into a text column instead of a real document reference —
          the same trap the Land certificate upload normalizes in
          _persist_embedded_certificate. The intake photo section was built
          that way first; the branch stays because it is the shape any future
          plain-file photo binding would take.

        Either way: upload the bytes properly and store the resulting
        document_id in record_image_document_id. A plain string (an existing
        document_id, or None) passes through unchanged."""
        value = record.pop("record_image_url", None)
        if not is_embedded_file(value):
            value = record.get("record_image_document_id")
        if not is_embedded_file(value):
            return
        record["record_image_document_id"] = await upload_embedded_file(
            value, record.get("created_by")
        )

    async def _sync_flattened_geo_names(self, record: dict) -> None:
        """Flatten geo_code_hierarchy_json into region/zone/woreda/kebele_name
        columns, since the search-result list only supports flat getattr()
        lookups (no JSON paths). Runs here rather than as a model-level
        SQLAlchemy validator because G2PGeo already owns a validator on
        geo_lowest_level_value_id, and SQLAlchemy does not allow a second
        validator for the same mapped attribute."""
        # Intake saves one section at a time. Saving Personal Information after
        # Address must not overwrite the already-persisted location projections
        # with None. An explicitly submitted empty ID still clears them.
        if "geo_lowest_level_value_id" not in record:
            return
        level_value_id = record.get("geo_lowest_level_value_id")
        levels = {"region": None, "zone": None, "woreda": None, "kebele": None}
        level_ids = {"woreda": None}
        # Country packs can use either Ethiopia-specific administrative names
        # or the generic hierarchy names used by the default sample pack.
        # Persist both shapes in the Farmer-facing region/zone/woreda/kebele
        # columns so list cards and filters do not depend on a particular pack.
        level_aliases = {
            "region": "region",
            "zone": "zone",
            "district": "zone",
            "woreda": "woreda",
            "ward": "woreda",
            "kebele": "kebele",
            "village": "kebele",
        }
        if level_value_id:
            from openg2p_registry_core.services import G2PGeoHierarchyService
            service = G2PGeoHierarchyService.get_component() or G2PGeoHierarchyService()
            hierarchy = await service.get_geo_hierarchy(level_value_id)
            for entry in (hierarchy or {}).get("hierarchy", []):
                mnemonic = (entry.get("level_mnemonic") or "").strip().lower()
                target = level_aliases.get(mnemonic)
                if target:
                    levels[target] = self._geo_display_name(entry)
                    if target in level_ids:
                        level_ids[target] = entry.get("level_value_id")
        record["region_name"] = levels["region"]
        record["zone_name"] = levels["zone"]
        record["woreda_name"] = levels["woreda"]
        record["kebele_name"] = levels["kebele"]
        record["woreda_level_value_id"] = level_ids["woreda"]

    async def post_approve(self, change_request: G2PRegisterChangeRequest, session):
        """Keep linked Household head data aligned with the approved Farmer."""
        if change_request.section_register_id != FARMER_REGISTER_ID:
            return

        from ..models import G2PRegisterFarmer

        farmer = (
            await session.execute(
                select(G2PRegisterFarmer).where(
                    G2PRegisterFarmer.internal_record_id
                    == change_request.internal_record_id
                )
            )
        ).scalar_one_or_none()
        if farmer:
            farmer.state = "APPROVED"
            source = str(change_request.change_request_source or "").upper()
            if not farmer.import_source and source in self._IMPORT_SOURCES:
                farmer.import_source = source
        await self._sync_linked_household_head(farmer, session)

    async def post_ingest(self, register_id, register_row, session):
        """Keep Household head data aligned after Farmer intake ingestion."""
        if register_id != FARMER_REGISTER_ID:
            return
        register_row.state = "APPROVED"
        if not register_row.import_source:
            # post_ingest is the direct ingestion/partner path. Intake-form
            # approvals use post_approve above and preserve INTAKE_FORM.
            register_row.import_source = "PARTNER"
        await self._sync_linked_household_head(register_row, session)

    async def _sync_linked_household_head(self, farmer, session):
        if not farmer:
            return

        if farmer.is_household_head and not farmer.link_internal_record_id:
            await self._create_household_for_head(farmer, session)

        if not farmer.link_internal_record_id:
            return

        from ..models import G2PRegisterFarmer, G2PRegisterHousehold

        household = (
            await session.execute(
                select(G2PRegisterHousehold).where(
                    G2PRegisterHousehold.internal_record_id
                    == farmer.link_internal_record_id
                )
            )
        ).scalar_one_or_none()
        if not household:
            return

        farmer_name = (farmer.record_name or "").strip()
        if farmer.is_household_head:
            await session.execute(
                update(G2PRegisterFarmer)
                .where(
                    G2PRegisterFarmer.link_internal_record_id
                    == farmer.link_internal_record_id,
                    G2PRegisterFarmer.internal_record_id
                    != farmer.internal_record_id,
                )
                .values(is_household_head=False)
            )
            household.household_head = farmer_name or None
        elif (
            farmer_name
            and (household.household_head or "").strip().casefold()
            == farmer_name.casefold()
        ):
            household.household_head = None

    async def _create_household_for_head(self, farmer, session) -> None:
        """Auto-create a minimal Household when a Farmer declares themself
        the household head and isn't linked to one yet — mirrors the legacy
        Odoo flow, where "Are you a household head?" = yes implicitly
        established the household (and cascaded the farmer's location to it).
        Household detail fields (size, income, etc.) are filled in afterward
        via the Household register's own edit/intake form.

        Mirrors the platform's own record-creation path (see
        openg2p_registry_core g2p_register_change_request_service.py
        insert_into_register / _handle_functional_record_id_generation):
        insert the row directly, then enqueue functional-id generation —
        the existing celery worker assigns the real HH-########## id
        exactly as it would for any other new Household record.
        """
        import uuid
        from datetime import datetime, timezone

        from openg2p_registry_core.models import G2PFunctionalIdGenerationQueue

        from ..models import G2PRegisterHousehold
        from .g2p_register_domain_service_household import (
            G2PRegisterDomainServiceHousehold,
        )

        household_internal_id = str(uuid.uuid4())
        # created_at/last_approved_at are TIMESTAMP WITHOUT TIME ZONE — a
        # tz-aware value makes asyncpg raise "can't subtract offset-naive and
        # offset-aware datetimes" on insert.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        approver = farmer.last_approved_by or farmer.created_by

        household = G2PRegisterHousehold(
            internal_record_id=household_internal_id,
            household_head=(farmer.record_name or "").strip() or None,
            record_status="ACTIVE",
            created_by=farmer.created_by,
            created_at=now,
            last_approved_by=approver,
            last_approved_at=now,
            latitude=farmer.latitude,
            longitude=farmer.longitude,
            altitude=farmer.altitude,
            plus_code=farmer.plus_code,
            address_line_1=farmer.address_line_1,
            address_line_2=farmer.address_line_2,
            postal_code=farmer.postal_code,
            country_code=farmer.country_code,
            geo_lowest_level_value_id=farmer.geo_lowest_level_value_id,
        )
        household_service = G2PRegisterDomainServiceHousehold()
        payload = {
            "household_head": household.household_head,
            "address_line_1": household.address_line_1,
            "address_line_2": household.address_line_2,
            "postal_code": household.postal_code,
            "country_code": household.country_code,
        }
        household.record_name = household_service.construct_record_name(payload)
        household.search_text = household_service.construct_search_text(payload)

        session.add(household)
        session.add(
            G2PFunctionalIdGenerationQueue(
                register_id=HOUSEHOLD_REGISTER_ID,
                internal_record_id=household_internal_id,
            )
        )
        await session.flush()

        farmer.link_internal_record_id = household_internal_id
        _logger.info(
            "Auto-created household %s for household-head farmer %s",
            household_internal_id,
            farmer.internal_record_id,
        )

    @staticmethod
    def _geo_display_name(entry: dict) -> str | None:
        """Return a readable geography label without damaging supplied names."""
        for key in (
            "level_value_display_name",
            "level_value_name",
            "display_name",
        ):
            value = str(entry.get(key) or "").strip()
            if value:
                return value

        mnemonic = str(entry.get("level_value_mnemonic") or "").strip()
        if not mnemonic:
            return None
        return mnemonic.replace("_", " ").replace("-", " ").title()

    def _validate_names(self, record: dict) -> None:
        """Mirror the name rules the intake form applies in the browser.

        widget-data-validation never reaches bulk import, the partner API or
        ingestion, so without this the "no partial or corrupt record" guarantee
        holds for browser traffic only.

        Format is checked on every path -- a name with digits in it is wrong
        however it arrived. Required is checked only on the interactive paths:
        roughly 6% of genuine Gen1 farmers have no first name at all, and
        rejecting those would block the migration rather than improve the data.
        """
        interactive = is_interactive(record)

        for field in NAME_FIELDS:
            # A key that was not submitted at all is a partial update of other
            # attributes, not an attempt to blank the name.
            if field not in record:
                continue
            value = record.get(field)
            text = "" if value is None else str(value).strip()

            if not text:
                if interactive and field in REQUIRED_NAME_FIELDS:
                    validation_error(f"{field} is required")
                continue

            if len(text) > NAME_MAX_LENGTH:
                validation_error(
                    f"{field} must be {NAME_MAX_LENGTH} characters or fewer"
                )
            if not matches(NAME_PATTERN, text):
                validation_error(
                    f"{field} may contain only letters (Latin or Ethiopic), "
                    "spaces, hyphens and apostrophes"
                )
            record[field] = text

    def _validate_birth_date(self, record: dict) -> None:
        birth_date = parse_date(record.get("birth_date"))
        if birth_date is not None and birth_date > date.today():
            validation_error("birth_date must not be in the future")

    def _validate_estimated_age(self, record: dict) -> None:
        birth_date = parse_date(record.get("birth_date"))
        estimated_age = as_int(record.get("estimated_age"))
        if birth_date is None or estimated_age is None:
            return
        computed_age = self._calculate_age(birth_date)
        if computed_age is not None and abs(estimated_age - computed_age) > 1:
            validation_error(
                "estimated_age must be consistent with birth_date within one year"
            )

    def _sync_ethiopian_birth_date(self, record: dict) -> None:
        """Keep birth_date (Gregorian) and birth_date_ec (Ethiopic) in step.

        Runs here rather than in the date widget so every entry path gets it --
        web intake, bulk ingestion, the partner API and file import all land in
        validate_domain_attributes, and only the first of those has a UI.

        Whichever side the enumerator filled derives the other. If both arrive,
        they must agree: silently rewriting one of two explicitly entered
        values would hide a data-entry error rather than surface it.
        """
        # Only touch the pair when the caller actually submitted at least one
        # of them. A partial update of, say, marital_status carries neither key
        # and must not have a birth date derived onto it.
        has_gc = "birth_date" in record
        has_ec = "birth_date_ec" in record
        if not has_gc and not has_ec:
            return

        gregorian = parse_date(record.get("birth_date"))
        raw_ec = record.get("birth_date_ec")
        ethiopic = parse_ethiopic(raw_ec)

        if raw_ec not in (None, "") and ethiopic is None:
            validation_error(
                "birth_date_ec must be an Ethiopic date in YYYY-MM-DD form"
            )

        if ethiopic is not None:
            try:
                converted = ethiopic_to_gregorian(*ethiopic)
            except ValueError as exc:
                validation_error(str(exc))
            if gregorian is None:
                record["birth_date"] = converted
            elif converted != gregorian:
                validation_error(
                    "birth_date_ec does not match birth_date "
                    f"({format_ethiopic(*ethiopic)} EC is {converted} GC, "
                    f"not {gregorian})"
                )
            # Normalize to the padded string form even when it round-trips, so
            # a legacy date value or an unpadded entry is rewritten on save.
            record["birth_date_ec"] = format_ethiopic(*ethiopic)
        elif gregorian is not None:
            record["birth_date_ec"] = gregorian_to_ethiopic_string(gregorian)

    def _populate_age_from_birth_date(self, record: dict) -> None:
        """Populate the stored Age when a Gregorian birth date is supplied."""
        birth_date = parse_date(record.get("birth_date"))
        if birth_date is not None and as_int(record.get("estimated_age")) is None:
            record["estimated_age"] = self._calculate_age(birth_date)

    @staticmethod
    def _calculate_age(birth_date: date) -> int | None:
        if not birth_date:
            return None
        today = date.today()
        return (
            today.year
            - birth_date.year
            - ((today.month, today.day) < (birth_date.month, birth_date.day))
        )

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for farmer")

        keys = [
            "functional_record_id",
            "state",
            "import_source",
            "first_name",
            "last_name",
            "foundational_id",
            "middle_name",
            "father_first_name",
            "given_name",
            "gender",
            "birth_date",
            "birth_date_ec",
            "marital_status",
            "occupation",
            "education_level",
            "language_spoken",
            "source_of_income",
            "is_household_head",
            "national_id_masked",
            "disability_type",
            "latitude",
            "longitude",
            "altitude",
            "plus_code",
            "address_line_1",
            "address_line_2",
            "postal_code",
            "country_code",
        ]
        search_text = []
        if extra:
            search_text.extend(
                str(value).strip() for value in extra if str(value).strip()
            )
        search_text.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(search_text).strip()

    def construct_record_name(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing record name for farmer")

        keys = ["first_name", "last_name"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()

    async def deduplicate_registry_records(
        self,
        check_id_documents: bool = True,
        check_foundational_id: bool = True,
        check_phones: bool = True,
        check_household_overlap: bool = True,
        reset_existing: bool = True,
    ) -> dict:
        """
        Scan all farmer registry records and flag duplicates, recreating Gen 1 deduplication behavior.
        Matches on:
        - Configured ID documents (id_type, value) from g2p_register_reg_ids
        - Foundational IDs from g2p_register_farmers
        - Phone numbers from g2p_register_farmer_phones
        - Household member overlap from g2p_register_household_members
        """
        _logger.info("Starting registry-wide deduplication scan...")
        all_duplicate_ids = set()
        match_entries = []
        breakdown = {
            "id_documents": 0,
            "foundational_id": 0,
            "phones": 0,
            "household_overlap": 0,
        }

        async with dbengine.get().begin() as conn:
            if reset_existing:
                _logger.info("Resetting existing is_duplicated flags")
                await conn.execute(
                    text("UPDATE public.g2p_register_farmers SET is_duplicated = FALSE WHERE is_duplicated = TRUE")
                )
                await conn.execute(
                    text("DELETE FROM public.dedup_results_register_records WHERE register_id = :reg_id"),
                    {"reg_id": FARMER_REGISTER_ID},
                )

            # 1. ID Documents check (Gen 1 style)
            if check_id_documents:
                id_doc_query = text(
                    """
                    SELECT 
                        reg_id.id_type,
                        reg_id.value,
                        array_agg(DISTINCT reg_id.link_internal_record_id) AS dup_ids
                    FROM public.g2p_register_reg_ids reg_id
                    JOIN public.g2p_register_farmers f ON f.internal_record_id = reg_id.link_internal_record_id
                    WHERE reg_id.status = 'VALID' 
                      AND reg_id.value IS NOT NULL 
                      AND TRIM(reg_id.value) != ''
                    GROUP BY reg_id.id_type, reg_id.value
                    HAVING count(DISTINCT reg_id.link_internal_record_id) > 1
                    """
                )
                result = await conn.execute(id_doc_query)
                for row in result.fetchall():
                    id_type, val, dup_ids = row[0], row[1], list(row[2])
                    all_duplicate_ids.update(dup_ids)
                    breakdown["id_documents"] += len(dup_ids)
                    for i in range(len(dup_ids)):
                        for j in range(i + 1, len(dup_ids)):
                            match_entries.append({
                                "register_id": FARMER_REGISTER_ID,
                                "primary_internal_record_id": dup_ids[i],
                                "duplicate_internal_record_id": dup_ids[j],
                                "match_criteria_type": f"ID_DOC:{id_type}",
                                "match_value": val,
                                "match_score": 100.0,
                            })

            # 2. Foundational ID check
            if check_foundational_id:
                foundational_query = text(
                    """
                    SELECT 
                        foundational_id, 
                        array_agg(DISTINCT internal_record_id) AS dup_ids
                    FROM public.g2p_register_farmers
                    WHERE foundational_id IS NOT NULL 
                      AND TRIM(foundational_id) != ''
                    GROUP BY foundational_id
                    HAVING count(DISTINCT internal_record_id) > 1
                    """
                )
                result = await conn.execute(foundational_query)
                for row in result.fetchall():
                    val, dup_ids = row[0], list(row[1])
                    all_duplicate_ids.update(dup_ids)
                    breakdown["foundational_id"] += len(dup_ids)
                    for i in range(len(dup_ids)):
                        for j in range(i + 1, len(dup_ids)):
                            match_entries.append({
                                "register_id": FARMER_REGISTER_ID,
                                "primary_internal_record_id": dup_ids[i],
                                "duplicate_internal_record_id": dup_ids[j],
                                "match_criteria_type": "FOUNDATIONAL_ID",
                                "match_value": val,
                                "match_score": 100.0,
                            })

            # 3. Phone Numbers check
            if check_phones:
                phone_query = text(
                    """
                    SELECT 
                        p.phone_number, 
                        array_agg(DISTINCT p.link_internal_record_id) AS dup_ids
                    FROM public.g2p_register_farmer_phones p
                    JOIN public.g2p_register_farmers f ON f.internal_record_id = p.link_internal_record_id
                    WHERE p.phone_number IS NOT NULL 
                      AND TRIM(p.phone_number) != ''
                    GROUP BY p.phone_number
                    HAVING count(DISTINCT p.link_internal_record_id) > 1
                    """
                )
                result = await conn.execute(phone_query)
                for row in result.fetchall():
                    val, dup_ids = row[0], list(row[1])
                    all_duplicate_ids.update(dup_ids)
                    breakdown["phones"] += len(dup_ids)
                    for i in range(len(dup_ids)):
                        for j in range(i + 1, len(dup_ids)):
                            match_entries.append({
                                "register_id": FARMER_REGISTER_ID,
                                "primary_internal_record_id": dup_ids[i],
                                "duplicate_internal_record_id": dup_ids[j],
                                "match_criteria_type": "PHONE_NUMBER",
                                "match_value": val,
                                "match_score": 100.0,
                            })

            # 4. Household Member Overlap
            if check_household_overlap:
                household_query = text(
                    """
                    SELECT 
                        f.internal_record_id AS individual_id,
                        array_agg(DISTINCT m.link_internal_record_id) AS household_ids
                    FROM public.g2p_register_household_members m
                    JOIN public.g2p_register_farmers f ON (f.foundational_id = m.foundational_id OR f.internal_record_id = m.internal_record_id)
                    WHERE m.link_internal_record_id IS NOT NULL
                    GROUP BY f.internal_record_id
                    HAVING count(DISTINCT m.link_internal_record_id) > 1
                    """
                )
                result = await conn.execute(household_query)
                for row in result.fetchall():
                    individual_id, household_ids = row[0], list(row[1])
                    all_duplicate_ids.add(individual_id)
                    breakdown["household_overlap"] += 1
                    match_entries.append({
                        "register_id": FARMER_REGISTER_ID,
                        "primary_internal_record_id": individual_id,
                        "duplicate_internal_record_id": individual_id,
                        "match_criteria_type": "HOUSEHOLD_OVERLAP",
                        "match_value": f"Appears in households: {', '.join(household_ids)}",
                        "match_score": 100.0,
                    })

            # 5. Mark all duplicate farmer records
            if all_duplicate_ids:
                dup_list = list(all_duplicate_ids)
                await conn.execute(
                    text("UPDATE public.g2p_register_farmers SET is_duplicated = TRUE WHERE internal_record_id = ANY(:ids)"),
                    {"ids": dup_list},
                )

            # 6. Save match details
            for entry in match_entries:
                await conn.execute(
                    text(
                        """
                        INSERT INTO public.dedup_results_register_records (
                            register_id, primary_internal_record_id, duplicate_internal_record_id,
                            match_criteria_type, match_value, match_score
                        ) VALUES (
                            :register_id, :primary_internal_record_id, :duplicate_internal_record_id,
                            :match_criteria_type, :match_value, :match_score
                        )
                        """
                    ),
                    entry,
                )

        _logger.info(f"Registry deduplication completed: {len(all_duplicate_ids)} duplicates found")
        return {
            "status": "SUCCESS",
            "total_duplicate_farmers": len(all_duplicate_ids),
            "duplicate_farmer_ids": list(all_duplicate_ids),
            "breakdown": breakdown,
            "total_pairs_recorded": len(match_entries),
        }

    async def get_deduplication_summary(self) -> dict:
        async with dbengine.get().begin() as conn:
            dup_count = (await conn.execute(
                text("SELECT count(*) FROM public.g2p_register_farmers WHERE is_duplicated = TRUE")
            )).scalar() or 0

            total_count = (await conn.execute(
                text("SELECT count(*) FROM public.g2p_register_farmers")
            )).scalar() or 0

            records_result = await conn.execute(
                text("SELECT match_criteria_type, count(*) FROM public.dedup_results_register_records GROUP BY match_criteria_type")
            )
            criteria_counts = {row[0]: row[1] for row in records_result.fetchall()}

            return {
                "total_farmers": total_count,
                "duplicated_farmers": dup_count,
                "unique_farmers": total_count - dup_count,
                "criteria_counts": criteria_counts,
            }

    async def reset_deduplication(self) -> dict:
        async with dbengine.get().begin() as conn:
            await conn.execute(
                text("UPDATE public.g2p_register_farmers SET is_duplicated = FALSE WHERE is_duplicated = TRUE")
            )
            await conn.execute(
                text("DELETE FROM public.dedup_results_register_records WHERE register_id = :reg_id"),
                {"reg_id": FARMER_REGISTER_ID},
            )
        return {"status": "SUCCESS", "message": "All duplicate flags and results reset successfully"}

