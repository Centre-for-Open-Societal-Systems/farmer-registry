-- Fail loudly when the OAN layer did not apply. The seed runs psql with
-- ON_ERROR_STOP=0, so a derivation that matched nothing (an upstream section
-- renamed or reshaped) would otherwise pass silently. This raises an ERROR in
-- the seed log naming what is missing.

DO $$
DECLARE
  missing text;
BEGIN
  SELECT string_agg(f, ', ') INTO missing
  FROM (VALUES
    ('oan_farmer_name', 'first_name_local'),
    ('oan_farmer_name', 'last_name_local'),
    ('oan_farmer_name', 'language_spoken'),
    ('oan_farmer_personal_details', 'birth_date'),
    ('oan_farmer_photo', 'farmer-photo'),
    ('oan_farmer_socio_economic_and_health', 'is_psnp_user'),
    ('oan_farmer_membership_details', 'primary_commodity'),
    ('oan_farmer_lands', 'land_id'),
    ('oan_farmer_lands', 'remark'),
    ('oan_farmer_livestock', 'production_type'),
    ('oan_farmer_livestock_intake', 'production_type'),
    ('oan_farmer_farm_inputs', 'amount_improved_seed_utilized'),
    ('oan_farmer_farm_inputs_intake', 'amount_improved_seed_utilized'),
    ('oan_farmer_socio_economic_and_health', 'source_of_income_other'),
    ('oan_farmer_household_lookup', 'is_household_head'),
    ('oan_household_information', 'father_included'),
    ('oan_farmer_location', 'farmer_geo_point'),
    ('oan_farmer_location', 'local_language'),
    ('oan_farmer_location', 'farmer_geo_hierarchy'),
    ('oan_farmer_photo', 'enumerator-position'),
    ('oan_farmer_lands', 'certificate_storage_id'),
    ('oan_farmer_crops', 'is_diseased'),
    ('oan_farmer_crops_intake', 'disease_type'),
    ('oan_farmer_livestock_intake', 'collected_date'),
    ('oan_farmer_farm_inputs_intake', 'machinery_types'),
    ('oan_farmer_socio_economic_and_health', 'income_sources'),
    ('oan_farmer_crops_intake', 'water_sources'),
    ('oan_farmer_livestock_intake', 'water_sources'),
    ('oan_farmer_farm_inputs_intake', 'finance_access_types'),
    ('oan_farmer_personal_identification', 'has_national_id'),
    ('oan_farmer_socio_economic_and_health', 'farming_type'),
    ('oan_household_information', 'other_farmer_in_household'),
    ('oan_farmer_household_lookup', 'is_household_head'),
    ('oan_household_information', 'number_of_male_members'),
    ('oan_household_information', 'number_of_female_members'),
    ('oan_farmer_documents', 'identity_document_1'),
    ('oan_farmer_documents', 'identity_document_type'),
    ('oan_farmer_phones', 'phone_number'),
    ('oan_farmer_personal_identification', 'foundational_id'),
    ('oan_farmer_personal_identification', 'rid'),
    ('oan_farmer_personal_identification', 'pula_id'),
    ('oan_farmer_land_summary', 'total_land_area'),
    ('oan_farmer_enumerator', 'enumerator_name')
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
  WHERE s.section_id LIKE 'oan\_%' AND NOT w ? 'widget';
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'OAN form layout names upstream widgets that do not exist: %', missing;
  END IF;

  SELECT string_agg(section_id, ', ') INTO missing
   FROM (VALUES ('oan_farmer_personal_identification'), ('oan_farmer_name'), ('oan_farmer_personal_details'),
                ('oan_farmer_socio_economic_and_health'),
               ('oan_farmer_membership_details'), ('oan_farmer_lands'), ('oan_farmer_livestock'),
               ('oan_farmer_farm_inputs'), ('oan_farmer_household_lookup'), ('oan_household_information'),
               ('oan_farmer_location'), ('oan_farmer_crops'), ('oan_farmer_phones'),
               ('oan_farmer_land_summary'), ('oan_farmer_enumerator'), ('oan_farmer_documents')) e(section_id)
  WHERE NOT EXISTS (SELECT 1 FROM "public"."g2p_register_ui_tab_sections" t WHERE t.section_id = e.section_id);
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'OAN sections not on any register tab: %', missing;
  END IF;

  SELECT string_agg(section_id, ', ') INTO missing
   FROM (VALUES ('oan_farmer_personal_identification'), ('oan_farmer_name'), ('oan_farmer_personal_details'),
                ('oan_farmer_socio_economic_and_health'),
               ('oan_farmer_membership_details'), ('oan_farmer_lands'), ('oan_farmer_livestock_intake'),
               ('oan_farmer_farm_inputs_intake'), ('oan_farmer_photo'),
               ('oan_household_information'), ('oan_farmer_location'), ('oan_farmer_crops_intake'),
               ('oan_farmer_phones'), ('oan_farmer_documents')) e(section_id)
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
             WHERE section_id LIKE 'oan\_%'
               AND jsonb_path_exists(section_ui_schema, 'lax $.** ? (@.widget == "oan-ethiopian-date")')) THEN
    RAISE EXCEPTION 'Obsolete read-only Ethiopian date widget remains in OAN metadata';
  END IF;

  -- A section replaced by an OAN one must not show twice.
  SELECT string_agg(section_id, ', ') INTO missing
  FROM (SELECT section_id FROM "public"."g2p_register_ui_tab_sections"
        UNION ALL SELECT section_id FROM "public"."g2p_intake_form_ui_tab_sections"
                  WHERE section_id <> 'farmer_household_lookup_section_01') t
  WHERE section_id IN ('farmer_household_lookup_section_01', 'farmer_farmer_location_section_03',
                       'farmer_crop_crop_details_section_01', 'farmer_crop_crop_details_intake_section_01',
                       'household_household_household_information_section_01',
                       'bc882922-9008-4902-8f4f-98db0fa8f9ad');
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'Upstream sections still attached next to their OAN replacement: %', missing;
  END IF;

  -- The household is asked on the farmer's intake form (20_layout.sql).
  SELECT string_agg(section_id, ', ') INTO missing
  FROM (VALUES ('oan_household_information'), ('household_household_household_member_section_02')) e(section_id)
  WHERE NOT EXISTS (SELECT 1 FROM "public"."g2p_intake_form_ui_tab_sections" t
                    WHERE t.section_id = e.section_id AND t.tab_id = 'a1a4d25a-1cd4-4356-abac-72482721');
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'Household sections not on the farmer intake form: %', missing;
  END IF;

  -- A new household can be entered, so the household lookup is optional (10_sections.sql).
  IF EXISTS (SELECT 1 FROM "public"."g2p_register_sections" s,
                   jsonb_array_elements(s."section_ui_schema" #> '{panels,0,panels,0,widgets}') w
              WHERE s."section_id" = 'oan_farmer_household_lookup'
                AND w ->> 'widget-id' = 'household_lookup' AND (w ->> 'widget-required')::boolean IS TRUE) THEN
    RAISE EXCEPTION 'The household lookup on the farmer form is still required';
  END IF;

  SELECT string_agg(tab_id || ':' || section_id, ', ') INTO missing
  FROM (VALUES
    ('farmer_farmer_tab', 'oan_farmer_personal_identification'),
    ('farmer_farmer_tab', 'oan_farmer_name'),
    ('farmer_farmer_tab', 'oan_farmer_personal_details')
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
    ('a1a4d25a-1cd4-4356-abac-72482721', 'oan_farmer_personal_identification'),
    ('a1a4d25a-1cd4-4356-abac-72482721', 'oan_farmer_name'),
    ('a1a4d25a-1cd4-4356-abac-72482721', 'oan_farmer_personal_details')
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
  WHERE section_id IN ('oan_farmer_personal_identification', 'oan_farmer_name', 'oan_farmer_personal_details')
  GROUP BY section_mnemonic
  HAVING count(*) > 1;
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'Personal Information section mnemonics are not unique: %', missing;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM "public"."g2p_register_sections"
    WHERE section_id = 'oan_farmer_personal_identification'
      AND section_ui_schema::text LIKE '%"widget": "oan-identity-verification"%'
  ) THEN
      RAISE EXCEPTION 'The Fayda verification widget is missing from the farmer Identity section';
  END IF;
  IF (
    SELECT count(*) <> 1 OR bool_or(
      w->>'widget' IS DISTINCT FROM 'display'
      OR w->>'widget-type' IS DISTINCT FROM 'display'
      OR w->>'widget-readonly' IS DISTINCT FROM 'true'
      OR w->>'widget-required' IS DISTINCT FROM 'false')
    FROM g2p_register_sections,
      jsonb_path_query(section_ui_schema, 'strict $.**') w
    WHERE section_id = 'oan_farmer_personal_identification'
      AND jsonb_typeof(w) = 'object' AND w ? 'widget'
      AND w->>'widget-id' = 'foundational_id'
  ) THEN
    RAISE EXCEPTION 'Popup-only FIN requires exactly one read-only display on the form';
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
        max(section_order) FILTER (WHERE section_id = 'oan_farmer_personal_identification') AS identity_order,
        max(section_order) FILTER (WHERE section_id = 'oan_farmer_name') AS name_order,
        max(section_order) FILTER (WHERE section_id = 'oan_farmer_personal_details') AS details_order
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
        max(section_order) FILTER (WHERE section_id = 'oan_farmer_personal_identification') AS identity_order,
        max(section_order) FILTER (WHERE section_id = 'oan_farmer_name') AS name_order,
        max(section_order) FILTER (WHERE section_id = 'oan_farmer_personal_details') AS details_order,
        max(section_order) FILTER (WHERE section_id = 'oan_farmer_photo') AS photo_order
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
