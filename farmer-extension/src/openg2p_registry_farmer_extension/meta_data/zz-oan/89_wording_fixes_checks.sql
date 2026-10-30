-- Fails when one of the 89_wording_fixes.sql texts reads the old way, when a
-- crop, livestock or farm-input land lookup carries literal English again, or
-- when a Farmer message lacks its closing full stop. Advisory at run time like
-- 88; the metadata replay runs it with ON_ERROR_STOP=1.

DO $$
DECLARE
  found text;
BEGIN
  SELECT string_agg(k, ', ' ORDER BY k) INTO found
  FROM (VALUES
    ('fayda_fin_hint', '12-digit FIN or 16-digit FAN'),
    ('country_code', 'Country (2-letter code)'),
    ('location_hierarchy', 'Region, zone, woreda and kebele'),
    ('source_of_income', 'Sources of income'),
    ('estimated_age', 'Estimated age (years)'),
    ('date_must_be_past', 'Choose today or an earlier date.'),
    ('bank_document', 'Bank document'),
    ('farmer_document', 'Farmer or cooperative document'),
    ('farmer_document_type', 'Farmer or cooperative document type'),
    ('farmer_document_1', 'Farmer or cooperative document 1'),
    ('land_document', 'Land document'),
    ('representative_document', 'Representative document'),
    ('other_document', 'Other document'),
    ('other_document_purpose', 'Purpose of other document'),
    ('is_household_head', 'Is the farmer the head of the household?'),
    ('farmer_household_lookup', 'Household link'),
    ('is_primary_cooperative_member', 'Member of a primary cooperative'),
    ('is_cooperative_union_member', 'Member of a cooperative union'),
    ('is_farmer_cluster_member', 'Member of a farmer cluster'),
    ('add_farm', 'Add land'),
    ('unit', 'Land size unit'),
    ('enumerator_name', 'Name'),
    ('enumerator_user_id', 'User ID'),
    ('data_collection_date', 'Collected on'),
    ('enumerator_latitude', 'Latitude when collected'),
    ('enumerator_longitude', 'Longitude when collected'),
    ('enumerator_altitude', 'Altitude when collected (m)'),
    ('enumerator_accuracy', 'GPS accuracy when collected (m)'),
    ('farmer_lands', 'Land records'),
    ('farmer_crops', 'Crop records'),
    ('farmer_livestocks', 'Livestock records'),
    ('farmer_farm_inputs', 'Farm input records'),
    ('farmer_memberships', 'Cooperative and cluster membership'),
    ('enumerator', 'Enumerator details'),
    ('farmer_identity_verification', 'Fayda ID verification'),
    ('farmer_land_summary', 'Land summary'),
    ('farmer_livestock', 'Livestock records'),
    ('farmer_membership', 'Cooperative and cluster membership'),
    ('farmer_enumerator', 'Enumerator details'),
    ('farmer_email', 'Email'),
    ('email', 'Email address'),
    ('email_format', 'Enter an address like name@example.org'),
    ('farmer_crops_intake', 'Crop records'),
    ('farmer_farm_inputs_intake', 'Farm input records'),
    ('farmer_livestock_intake', 'Livestock records'),
    ('land', 'Land'),
    ('search_land', 'Search land...'),
    ('select_land', 'Select land'),
    ('INTAKE_FORM', 'Intake form'),
    ('NEVER_ATTEND', 'Never attended')) AS want(k, v)
  WHERE NOT EXISTS (SELECT 1 FROM "public"."registry_languages" l
                    WHERE l."is_default" AND l."domain_translation"::jsonb ->> want.k = want.v);
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'A label does not have its wording fix: %', found;
  END IF;

  -- Every Farmer message ends with a full stop.
  SELECT string_agg(k, ', ' ORDER BY k) INTO found
  FROM unnest(ARRAY['ethiopic_script_only', 'phone_ethiopian_mobile', 'land_size_positive', 'size_of_group_helptext',
                    'is_head_helptext', 'relationship_to_the_head_helptext', 'household_lookup_helptext',
                    'name_letters_only', 'fayda_fin_format', 'fayda_rid_format', 'country_code_format',
                    'plus_code_format', 'date_must_be_past']) k
  WHERE NOT EXISTS (SELECT 1 FROM "public"."registry_languages" l
                    WHERE l."is_default" AND l."domain_translation"::jsonb ->> k ~ '[.]$');
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'A message does not end with a full stop: %', found;
  END IF;

  -- The land lookup uses keys, not literal English.
  SELECT string_agg(s.section_id, ', ') INTO found
  FROM "public"."g2p_register_sections" s
  WHERE s.section_id IN ('farmer_crops', 'farmer_crops_intake', 'farmer_livestock', 'farmer_livestock_intake',
                         'farmer_farm_inputs', 'farmer_farm_inputs_intake')
    AND s.section_ui_schema::text ~ '"(widget-label|search_placeholder|select_record_label)": "(Land|Search land[.]*|Select land)"';
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'A land lookup carries literal English: %', found;
  END IF;

  SELECT string_agg(s.section_id, ', ') INTO found
  FROM "public"."g2p_register_sections" s
  WHERE s.section_id IN ('farmer_crops', 'farmer_crops_intake', 'farmer_livestock', 'farmer_livestock_intake',
                         'farmer_farm_inputs', 'farmer_farm_inputs_intake')
    AND NOT (s.section_ui_schema::text LIKE '%"search_land"%'
             AND s.section_ui_schema::text LIKE '%"select_land"%'
             AND s.section_ui_schema::text LIKE '%"land"%');
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'A land lookup lacks its translation keys: %', found;
  END IF;

  -- A section title is not also the name of its tab.
  SELECT string_agg(p.title_key, ', ') INTO found
  FROM (VALUES ('farmer_lands', 'farmer_lands_tab'), ('farmer_crops', 'farmer_crops_tab'),
               ('farmer_livestocks', 'farmer_livestocks_tab'), ('farmer_farm_inputs', 'farmer_farm_inputs_tab'),
               ('farmer_memberships', 'farmer_memberships_tab')) AS p(title_key, tab_key)
  JOIN "public"."registry_languages" l ON l."is_default"
  WHERE l."domain_translation"::jsonb ->> p.title_key = l."domain_translation"::jsonb ->> p.tab_key;
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'A section title repeats its tab name: %', found;
  END IF;

  IF EXISTS (SELECT 1 FROM "public"."g2p_register_definitions" r
             WHERE r."register_id" = '4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb'
               AND r."register_subject" IS DISTINCT FROM 'Livestock') THEN
    RAISE EXCEPTION 'The livestock register must be named Livestock';
  END IF;
END $$;
