-- Fail loudly when the OAN layer did not apply. The farmer seed runs psql with
-- ON_ERROR_STOP=0, so a derivation that matched nothing (an upstream section
-- renamed or reshaped) would otherwise pass silently. This raises an ERROR in
-- the seed log naming what is missing; the OAN entrypoint then runs this file
-- once more with ON_ERROR_STOP=1, so a failed check fails the seed job.

-- The OAN-owned sections, by id (10, 12, 15 and 18_*.sql). Session-local.
CREATE OR REPLACE FUNCTION pg_temp.oan_section_ids() RETURNS text[] LANGUAGE sql IMMUTABLE AS $$
  SELECT ARRAY[
    'farmer_identity', 'farmer_identity_verification', 'farmer_name', 'farmer_personal_details',
    'farmer_socio_economic_health', 'farmer_location', 'farmer_photo', 'farmer_phones', 'farmer_documents',
    'farmer_household_lookup', 'household_information', 'farmer_membership', 'farmer_lands',
    'farmer_land_summary', 'farmer_crops', 'farmer_crops_intake', 'farmer_livestock', 'farmer_livestock_intake',
    'farmer_farm_inputs', 'farmer_farm_inputs_intake', 'farmer_enumerator']
$$;

-- Names: an OAN section's id, mnemonic and UI section-id are one string; an
-- OAN attachment is <tab_id>__<section_id> on a register tab and
-- farmer_intake__ / household_intake__<section_id> on an intake form
-- (20_layout.sql); and no OAN row keeps the retired "oan_" prefix
-- (22_retired_rows.sql removes the known ones).
DO $$
DECLARE
  found text;
BEGIN
  SELECT string_agg(id, ', ') INTO found FROM (
    SELECT 'section ' || section_id AS id FROM "public"."g2p_register_sections" WHERE section_id LIKE 'oan\_%'
    UNION ALL SELECT 'register tab ' || tab_id FROM "public"."g2p_register_ui_tabs" WHERE tab_id LIKE 'oan\_%'
    UNION ALL SELECT 'register attachment ' || tab_section_id FROM "public"."g2p_register_ui_tab_sections"
              WHERE tab_section_id LIKE 'oan\_%' OR section_id LIKE 'oan\_%'
    UNION ALL SELECT 'intake attachment ' || tab_section_id FROM "public"."g2p_intake_form_ui_tab_sections"
              WHERE tab_section_id LIKE 'oan\_%' OR section_id LIKE 'oan\_%') o;
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'OAN rows under retired oan_ ids remain (add them to 22_retired_rows.sql): %', found;
  END IF;

  -- Data saved under a retired section id would be invisible on the forms;
  -- 21_renamed_section_data.sql moves it to the current id.
  SELECT string_agg(id, ', ') INTO found FROM (
    SELECT 'record documents under ' || section_id AS id FROM "public"."g2p_register_section_documents"
    WHERE section_id LIKE 'oan\_%' GROUP BY section_id
    UNION ALL SELECT 'intake documents under ' || section_id FROM "public"."g2p_intake_section_documents"
    WHERE section_id LIKE 'oan\_%' GROUP BY section_id
    UNION ALL SELECT 'change requests under ' || section_id FROM "public"."g2p_register_change_requests"
    WHERE section_id LIKE 'oan\_%' GROUP BY section_id) o;
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Data under retired oan_ section ids remains (add the id to 21_renamed_section_data.sql): %', found;
  END IF;

  SELECT string_agg(e.section_id, ', ') INTO found
  FROM unnest(pg_temp.oan_section_ids()) e(section_id)
  LEFT JOIN "public"."g2p_register_sections" s ON s.section_id = e.section_id
  WHERE s.section_id IS NULL
     OR s.section_mnemonic IS DISTINCT FROM s.section_id
     OR s.section_ui_schema->>'section-id' IS DISTINCT FROM s.section_id;
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'OAN sections missing, or with a mnemonic or UI section-id other than their id: %', found;
  END IF;

  SELECT string_agg(tab_section_id, ', ') INTO found FROM (
    SELECT tab_section_id FROM "public"."g2p_register_ui_tab_sections"
    WHERE section_id = ANY (pg_temp.oan_section_ids())
      AND tab_section_id IS DISTINCT FROM tab_id || '__' || section_id
    UNION ALL
    SELECT tab_section_id FROM "public"."g2p_intake_form_ui_tab_sections"
    WHERE section_id = ANY (pg_temp.oan_section_ids())
      AND tab_section_id IS DISTINCT FROM
          CASE tab_id WHEN 'a1a4d25a-1cd4-4356-abac-72482721' THEN 'farmer_intake__'
                      WHEN '9055ab43-c85d-4833-bd00-ca657bb72651' THEN 'household_intake__' END || section_id) o;
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'OAN attachments not named <tab>__<section>: %', found;
  END IF;

  -- Ingestion and outgestion rows: readable ids; the mnemonics, event type
  -- and topic name the connector and the subscribers use are unchanged.
  IF NOT EXISTS (SELECT 1 FROM "public"."data_models"
                 WHERE data_model_id = 'odk_to_farmer_intake' AND data_model_mnemonic = 'FARMER_ODK_MODEL')
     OR NOT EXISTS (SELECT 1 FROM "public"."incoming_model_key_paths"
                    WHERE key_path_id = 'odk_to_farmer_intake_key_path' AND data_model_id = 'odk_to_farmer_intake')
     OR NOT EXISTS (SELECT 1 FROM "public"."incoming_model_semantic_patterns"
                    WHERE semantic_pattern_id = 'odk_to_farmer_intake_pattern' AND data_model_id = 'odk_to_farmer_intake'
                      AND raw_payload_enricher_class = 'OdkToFarmerIntakeEnricher')
     OR NOT EXISTS (SELECT 1 FROM "public"."incoming_templates" t
                    JOIN "public"."g2p_registry_documents" d ON d.document_id = t.template_document_id
                    WHERE t.template_id = 'odk_to_farmer_intake_template' AND t.data_model_id = 'odk_to_farmer_intake'
                      AND d.document_store_id = 'odk_to_farmer_intake.j2') THEN
    RAISE EXCEPTION 'ODK ingestion rows odk_to_farmer_intake* are missing or inconsistent (60_odk_ingestion.sql)';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM "public"."outgoing_templates" t
                 JOIN "public"."g2p_registry_documents" d ON d.document_id = t.template_document_id
                 WHERE t.template_id = 'OUT-TMPL-1' AND d.document_id = 'farmer_dci_search_response_document'
                   AND d.document_store_id = 'farmer_dci_search_response.j2')
     OR NOT EXISTS (SELECT 1 FROM "public"."outgoing_templates" t
                    JOIN "public"."g2p_registry_documents" d ON d.document_id = t.template_document_id
                    WHERE t.template_id = 'farmer_reference_changed_v1_template'
                      AND t.data_model_id = '873c2342-cfde-5db4-9f9f-6e491a5001f7'
                      AND d.document_store_id = 'farmer_reference_changed_v1.j2')
     OR NOT EXISTS (SELECT 1 FROM "public"."outgoing_topics"
                    WHERE topic_id = 'farmer_reference_changed_v1_topic'
                      AND data_model_id = '873c2342-cfde-5db4-9f9f-6e491a5001f7'
                      AND websub_topic = 'oan.farmer-reference.changed.v1') THEN
    RAISE EXCEPTION 'Outgestion rows (OUT-TMPL-1, farmer_reference_changed_v1_*) are missing or inconsistent (50_outgestion.sql)';
  END IF;
END $$;

-- No section may appear twice on a tab, on the record or on a form, and the
-- intake forms are the farmer's and the household's only. These are generic:
-- they catch any leftover row, not a fixed list of ids.
DO $$
DECLARE
  found text;
BEGIN
  SELECT string_agg(tab_id || ':' || section_id || ' x' || n, ', ') INTO found
  FROM (SELECT tab_id, section_id, count(*) AS n
        FROM "public"."g2p_intake_form_ui_tab_sections" GROUP BY tab_id, section_id HAVING count(*) > 1) d;
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Sections attached more than once to an intake tab: %', found;
  END IF;

  SELECT string_agg(tab_id || ':' || section_id || ' x' || n, ', ') INTO found
  FROM (SELECT tab_id, section_id, count(*) AS n
        FROM "public"."g2p_register_ui_tab_sections" GROUP BY tab_id, section_id HAVING count(*) > 1) d;
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Sections attached more than once to a register tab: %', found;
  END IF;

  SELECT string_agg(form_id, ', ') INTO found
  FROM "public"."g2p_intake_form_definitions"
  WHERE form_id NOT IN ('a1a4d25a-1cd4-4356-abac-8782382649', '9055ab43-c85d-4833-bd00-ca657bb72650');
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Unexpected intake forms: %', found;
  END IF;

  SELECT string_agg(tab_id, ', ') INTO found
  FROM "public"."g2p_intake_form_ui_tabs"
  WHERE tab_id NOT IN ('a1a4d25a-1cd4-4356-abac-72482721', '9055ab43-c85d-4833-bd00-ca657bb72651');
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Unexpected intake tabs: %', found;
  END IF;

  -- The farmer intake form asks each thing once: the OAN sections, and the
  -- upstream ones OAN does not replace. An upstream row next to its OAN copy
  -- means 20_layout.sql's detach did not run.
  SELECT string_agg(tab_section_id || '->' || section_id, ', ') INTO found
  FROM "public"."g2p_intake_form_ui_tab_sections"
  WHERE tab_id = 'a1a4d25a-1cd4-4356-abac-72482721'
    AND section_id <> ALL (pg_temp.oan_section_ids())
    AND section_id <> 'household_household_household_member_section_02';
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Rows on the farmer intake tab that no current seed writes: %', found;
  END IF;
END $$;

DO $$
DECLARE
  missing text;
BEGIN
  SELECT string_agg(f, ', ') INTO missing
  FROM (VALUES
    ('farmer_name', 'first_name_local'),
    ('farmer_name', 'last_name_local'),
    ('farmer_name', 'language_spoken'),
    ('farmer_personal_details', 'birth_date'),
    ('farmer_photo', 'farmer-photo'),
    ('farmer_socio_economic_health', 'is_psnp_user'),
    ('farmer_membership', 'primary_commodity'),
    ('farmer_lands', 'land_id'),
    ('farmer_lands', 'remark'),
    ('farmer_livestock', 'production_type'),
    ('farmer_livestock_intake', 'production_type'),
    ('farmer_farm_inputs', 'amount_improved_seed_utilized'),
    ('farmer_farm_inputs_intake', 'amount_improved_seed_utilized'),
    ('farmer_socio_economic_health', 'source_of_income_other'),
    ('farmer_household_lookup', 'is_household_head'),
    ('household_information', 'father_included'),
    ('farmer_location', 'farmer_geo_point'),
    ('farmer_location', 'local_language'),
    ('farmer_location', 'farmer_geo_hierarchy'),
    ('farmer_photo', 'enumerator-position'),
    ('farmer_lands', 'certificate_storage_id'),
    ('farmer_crops', 'is_diseased'),
    ('farmer_crops_intake', 'disease_type'),
    ('farmer_livestock_intake', 'collected_date'),
    ('farmer_farm_inputs_intake', 'machinery_types'),
    ('farmer_socio_economic_health', 'income_sources'),
    ('farmer_crops_intake', 'water_sources'),
    ('farmer_livestock_intake', 'water_sources'),
    ('farmer_farm_inputs_intake', 'finance_access_types'),
    ('farmer_identity', 'has_national_id'),
    ('farmer_socio_economic_health', 'farming_type'),
    ('household_information', 'other_farmer_in_household'),
    ('farmer_household_lookup', 'is_household_head'),
    ('household_information', 'number_of_male_members'),
    ('household_information', 'number_of_female_members'),
    ('farmer_documents', 'identity_document_1'),
    ('farmer_documents', 'identity_document_type'),
    ('farmer_phones', 'phone_number'),
    ('farmer_identity', 'foundational_id'),
    ('farmer_identity', 'rid'),
    ('farmer_identity', 'pula_id'),
    ('farmer_land_summary', 'total_land_area'),
    ('farmer_enumerator', 'enumerator_name')
  ) e(section_id, field)
  CROSS JOIN LATERAL (SELECT e.section_id || '.' || e.field AS f) n
  WHERE NOT EXISTS (
    SELECT 1 FROM "public"."g2p_register_sections" s
    WHERE s.section_id = e.section_id
      AND jsonb_path_exists(s.section_ui_schema,
            'lax $.** ? (@."widget-id" == $f || @."column-key" == $f)',
            jsonb_build_object('f', e.field)));
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'OAN metadata layer incomplete, missing: %', missing;
  END IF;

  -- A form-layout widget naming an upstream widget-id that upstream no longer
  -- has comes out without a "widget" type (12_form_sections.sql).
  SELECT string_agg(DISTINCT s.section_id || '.' || (w->>'widget-id'), ', ') INTO missing
  FROM "public"."g2p_register_sections" s,
       jsonb_path_query(s.section_ui_schema, 'lax $.**.widgets[*]') w
  WHERE s.section_id = ANY (pg_temp.oan_section_ids()) AND NOT w ? 'widget';
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'OAN form layout names upstream widgets that do not exist: %', missing;
  END IF;

  SELECT string_agg(section_id, ', ') INTO missing
   FROM (VALUES ('farmer_identity'), ('farmer_name'), ('farmer_personal_details'),
                ('farmer_socio_economic_health'),
               ('farmer_membership'), ('farmer_lands'), ('farmer_livestock'),
               ('farmer_farm_inputs'), ('farmer_household_lookup'), ('household_information'),
               ('farmer_location'), ('farmer_crops'), ('farmer_phones'),
               ('farmer_land_summary'), ('farmer_enumerator'), ('farmer_documents')) e(section_id)
  WHERE NOT EXISTS (SELECT 1 FROM "public"."g2p_register_ui_tab_sections" t WHERE t.section_id = e.section_id);
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'OAN sections not on any register tab: %', missing;
  END IF;

  SELECT string_agg(section_id, ', ') INTO missing
   FROM (VALUES ('farmer_identity'), ('farmer_name'), ('farmer_personal_details'),
                ('farmer_socio_economic_health'),
               ('farmer_membership'), ('farmer_lands'), ('farmer_livestock_intake'),
               ('farmer_farm_inputs_intake'), ('farmer_photo'),
               ('household_information'), ('farmer_location'), ('farmer_crops_intake'),
               ('farmer_phones'), ('farmer_documents')) e(section_id)
  WHERE NOT EXISTS (SELECT 1 FROM "public"."g2p_intake_form_ui_tab_sections" t WHERE t.section_id = e.section_id);
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'OAN sections not on the intake form: %', missing;
  END IF;

  -- Every entered date, including child/table fields, uses the same calendar.
  SELECT string_agg(DISTINCT s.section_id || '.' || COALESCE(w->>'widget-id', w->>'column-key'), ', ')
    INTO missing
  FROM "public"."g2p_register_sections" s,
       jsonb_path_query(s.section_ui_schema,
         'lax $.** ? (@.widget == "date" || @.widget == "oan-ethiopian-date-input")') w
  WHERE COALESCE((w->>'widget-readonly')::boolean, false) = false
    AND w->>'widget-variant' IS DISTINCT FROM 'ethiopian';
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'Staff-entered dates missing the Ethiopian calendar variant: %', missing;
  END IF;

  IF EXISTS (SELECT 1 FROM "public"."g2p_register_sections"
             WHERE section_id = ANY (pg_temp.oan_section_ids())
               AND jsonb_path_exists(section_ui_schema, 'lax $.** ? (@.widget == "oan-ethiopian-date")')) THEN
    RAISE EXCEPTION 'Obsolete read-only Ethiopian date widget remains in OAN metadata';
  END IF;

  -- A section replaced by an OAN one must not show twice.
  SELECT string_agg(section_id, ', ') INTO missing
  FROM (SELECT section_id FROM "public"."g2p_register_ui_tab_sections"
        UNION ALL SELECT section_id FROM "public"."g2p_intake_form_ui_tab_sections") t
  WHERE section_id IN ('farmer_household_lookup_section_01', 'farmer_farmer_location_section_03',
                       'farmer_crop_crop_details_section_01', 'farmer_crop_crop_details_intake_section_01',
                       'household_household_household_information_section_01',
                       'bc882922-9008-4902-8f4f-98db0fa8f9ad');
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'Upstream sections still attached next to their OAN replacement: %', missing;
  END IF;

  -- The household is asked on the farmer's intake form (20_layout.sql).
  SELECT string_agg(section_id, ', ') INTO missing
  FROM (VALUES ('household_information'), ('household_household_household_member_section_02')) e(section_id)
  WHERE NOT EXISTS (SELECT 1 FROM "public"."g2p_intake_form_ui_tab_sections" t
                    WHERE t.section_id = e.section_id AND t.tab_id = 'a1a4d25a-1cd4-4356-abac-72482721');
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'Household sections not on the farmer intake form: %', missing;
  END IF;

  -- A new household can be entered, so the household lookup is optional (10_sections.sql).
  IF EXISTS (SELECT 1 FROM "public"."g2p_register_sections" s,
                   jsonb_array_elements(s."section_ui_schema" #> '{panels,0,panels,0,widgets}') w
              WHERE s."section_id" = 'farmer_household_lookup'
                AND w ->> 'widget-id' = 'household_lookup' AND (w ->> 'widget-required')::boolean IS TRUE) THEN
    RAISE EXCEPTION 'The household lookup on the farmer form is still required';
  END IF;

  SELECT string_agg(tab_id || ':' || section_id, ', ') INTO missing
  FROM (VALUES
    ('farmer_farmer_tab', 'farmer_identity'),
    ('farmer_farmer_tab', 'farmer_name'),
    ('farmer_farmer_tab', 'farmer_personal_details')
  ) e(tab_id, section_id)
  WHERE NOT EXISTS (
    SELECT 1 FROM "public"."g2p_register_ui_tab_sections" t
    WHERE t."tab_id" = e.tab_id AND t."section_id" = e.section_id
  );
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'Personal Information sections are not placed on the Farmer register tab: %', missing;
  END IF;

  SELECT string_agg(tab_id || ':' || section_id, ', ') INTO missing
  FROM (VALUES
    ('a1a4d25a-1cd4-4356-abac-72482721', 'farmer_identity'),
    ('a1a4d25a-1cd4-4356-abac-72482721', 'farmer_name'),
    ('a1a4d25a-1cd4-4356-abac-72482721', 'farmer_personal_details')
  ) e(tab_id, section_id)
  WHERE NOT EXISTS (
    SELECT 1 FROM "public"."g2p_intake_form_ui_tab_sections" t
    WHERE t."tab_id" = e.tab_id AND t."section_id" = e.section_id
  );
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'Personal Information sections are not placed on the Farmer intake tab: %', missing;
  END IF;

  SELECT string_agg(section_mnemonic, ', ') INTO missing
  FROM "public"."g2p_register_sections"
  WHERE section_id IN ('farmer_identity', 'farmer_name', 'farmer_personal_details')
  GROUP BY section_mnemonic
  HAVING count(*) > 1;
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'Personal Information section mnemonics are not unique: %', missing;
  END IF;

  -- The Fayda ID is typed by staff (approval is the control); verification is
  -- the platform's id-authentication widget on the farmer's record only.
  IF (
    SELECT count(*) <> 1 OR bool_or(w->>'widget' IS DISTINCT FROM 'text' OR (w->>'widget-readonly')::boolean IS TRUE)
    FROM g2p_register_sections, jsonb_path_query(section_ui_schema, 'strict $.**') w
    WHERE section_id = 'farmer_identity'
      AND jsonb_typeof(w) = 'object' AND w ? 'widget' AND w->>'widget-id' = 'foundational_id'
  ) THEN
    RAISE EXCEPTION 'The Fayda ID on the Identity section must be one editable text widget';
  END IF;
  IF EXISTS (SELECT 1 FROM g2p_register_sections
             WHERE jsonb_path_exists(section_ui_schema, 'lax $.** ? (@.widget == "oan-identity-verification")')) THEN
    RAISE EXCEPTION 'The retired OAN verification popup widget is still configured';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM "public"."g2p_register_ui_tab_sections" t
    JOIN "public"."g2p_register_sections" s ON s.section_id = t.section_id
    WHERE t.tab_id = 'farmer_farmer_tab' AND t.section_id = 'farmer_identity_verification'
      AND jsonb_path_exists(s.section_ui_schema, 'lax $.** ? (@.widget == "id-authentication")')
  ) THEN
    RAISE EXCEPTION 'The id-authentication section is not on the farmer record tab';
  END IF;
  IF (SELECT count(*) FROM "public"."g2p_register_ui_tab_sections" t
      JOIN "public"."g2p_register_sections" s ON s.section_id = t.section_id
      WHERE t.register_id = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd'
        AND jsonb_path_exists(s.section_ui_schema, 'lax $.** ? (@.widget == "id-authentication")')) <> 1 THEN
    RAISE EXCEPTION 'The farmer record must have exactly one id-authentication section';
  END IF;
  -- Every dropdown's options come from Master Data (widget-data-source type
  -- "api", service "attributes"); a yes/no is a boolean, not a list.
  IF EXISTS (
    SELECT 1 FROM "public"."g2p_register_sections", jsonb_path_query(section_ui_schema, 'strict $.**') w
    WHERE section_id = ANY (pg_temp.oan_section_ids())
      AND jsonb_typeof(w) = 'object' AND w->>'widget' IN ('select', 'multi-select')
      AND w->'widget-data-source'->>'type' = 'static'
      AND EXISTS (SELECT 1 FROM jsonb_array_elements(w->'widget-data-source'->'options') o
                  WHERE jsonb_typeof(o->'value') <> 'boolean')
  ) THEN
    RAISE EXCEPTION 'A choice list is written in the registry metadata; every dropdown comes from Master Data';
  END IF;
  IF EXISTS (SELECT 1 FROM "public"."g2p_intake_form_ui_tab_sections"
             WHERE section_id = 'farmer_identity_verification') THEN
    RAISE EXCEPTION 'Record verification must not be on the intake form; core authenticates register records';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM "public"."g2p_intake_form_ui_tab_sections"
                 WHERE tab_id = 'a1a4d25a-1cd4-4356-abac-72482721' AND section_id = 'farmer_household_lookup') THEN
    RAISE EXCEPTION 'The household lookup with the household-head question is not on the farmer intake form';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM "public"."g2p_register_definitions"
    WHERE register_id = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND requires_registrant_authentication
  ) THEN
    RAISE EXCEPTION 'Fayda Verify must be enabled; this flag is not a finalize verification gate';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM (
      SELECT
        max(section_order) FILTER (WHERE section_id = 'farmer_identity') AS identity_order,
        max(section_order) FILTER (WHERE section_id = 'farmer_name') AS name_order,
        max(section_order) FILTER (WHERE section_id = 'farmer_personal_details') AS details_order
      FROM "public"."g2p_register_ui_tab_sections"
      WHERE tab_id = 'farmer_farmer_tab'
    ) o
    WHERE NOT (identity_order < name_order AND name_order < details_order)
  ) THEN
    RAISE EXCEPTION 'Farmer register Personal Information sections are out of order';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM (
      SELECT
        max(section_order) FILTER (WHERE section_id = 'farmer_identity') AS identity_order,
        max(section_order) FILTER (WHERE section_id = 'farmer_name') AS name_order,
        max(section_order) FILTER (WHERE section_id = 'farmer_personal_details') AS details_order,
        max(section_order) FILTER (WHERE section_id = 'farmer_photo') AS photo_order
      FROM "public"."g2p_intake_form_ui_tab_sections"
      WHERE tab_id = 'a1a4d25a-1cd4-4356-abac-72482721'
    ) o
    WHERE NOT (identity_order < name_order AND name_order < details_order AND details_order < photo_order)
  ) THEN
    RAISE EXCEPTION 'Farmer intake Personal Information sections are out of order before photo';
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.g2p_register_sections s,
      jsonb_path_query(s.section_ui_schema,
        'lax $.** ? (@.widget == "select")') w
    WHERE w #>> '{widget-data-source,service}' = 'attributes'
      AND w #>> '{widget-data-source,valueKey}' = 'value_id'
  ) THEN
    RAISE EXCEPTION 'MDS-backed selects must store value_code for the core validator';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.g2p_register_sections s,
      jsonb_path_query(s.section_ui_schema,
        'lax $.** ? (@."column-key" == "year_of_acquisition" || @."widget-id" == "year_of_acquisition")') w
    WHERE (w #>> '{widget-data-validation,min}') IS DISTINCT FROM '1900'
       OR (w #>> '{widget-data-validation,max}') IS DISTINCT FROM EXTRACT(YEAR FROM CURRENT_DATE)::integer::text
  ) THEN
    RAISE EXCEPTION 'Year of Acquisition widgets must allow 1900 through the current year';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.g2p_register_sections s,
      jsonb_path_query(s.section_ui_schema,
        'lax $.** ? (@."column-key" == "collected_date" || @."widget-id" == "collected_date")') w
    WHERE (w #>> '{widget-data-format,dateConstraint}') IS DISTINCT FROM 'past-only'
  ) THEN
    RAISE EXCEPTION 'Livestock Count Date widgets must block future dates';
  END IF;
END $$;
