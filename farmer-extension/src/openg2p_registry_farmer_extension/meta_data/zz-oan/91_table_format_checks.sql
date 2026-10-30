-- Fails the seed when the Phones, Land summary, Lands, Crops, Livestock, Farm
-- inputs and Enumerator presentation (10, 15, 16, 17 and 87_table_text.sql)
-- did not apply. Like 90_checks.sql, it raises an ERROR the seed log shows, and
-- the metadata replay runs it with ON_ERROR_STOP=1.

DO $$
DECLARE
  found text;
BEGIN
  -- The land summary numbers keep two decimals, the enumerator position keeps
  -- six (latitude, longitude) and one (altitude, accuracy); the date is dd/mm/yyyy.
  SELECT string_agg(id, ', ') INTO found FROM (
    SELECT r.section_id || '.' || r.widget_id AS id
    FROM (VALUES
      ('farmer_land_summary', 'total_land_area', 2), ('farmer_land_summary', 'total_land_owned_area', 2),
      ('farmer_land_summary', 'total_land_rent_area', 2), ('farmer_land_summary', 'total_land_crop_sharing_area', 2),
      ('farmer_enumerator', 'enumerator_latitude', 6), ('farmer_enumerator', 'enumerator_longitude', 6),
      ('farmer_enumerator', 'enumerator_altitude', 1), ('farmer_enumerator', 'enumerator_accuracy', 1)
    ) r(section_id, widget_id, places)
    WHERE NOT EXISTS (
      SELECT 1 FROM "public"."g2p_register_sections" s,
        jsonb_path_query(s.section_ui_schema::jsonb, 'lax $.** ? (@."widget-id" != null)') w
      WHERE s.section_id = r.section_id AND w ->> 'widget-id' = r.widget_id
        AND (w #>> '{widget-data-format,decimalPlaces}')::int = r.places)) m;
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Numbers without their decimal places: %', found;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM "public"."g2p_register_sections" s,
      jsonb_path_query(s.section_ui_schema::jsonb, 'lax $.** ? (@."widget-id" == "data_collection_date")') w
    WHERE s.section_id = 'farmer_enumerator' AND w #>> '{widget-data-format,dateFormat}' = 'DD/MM/YYYY') THEN
    RAISE EXCEPTION 'The enumerator collection date has no date format';
  END IF;

  -- Land ownership is a read-only choice with the three derived codes.
  IF NOT EXISTS (
    SELECT 1 FROM "public"."g2p_register_sections" s,
      jsonb_path_query(s.section_ui_schema::jsonb, 'lax $.** ? (@."widget-id" == "land_ownership")') w
    WHERE s.section_id = 'farmer_land_summary' AND w ->> 'widget' = 'select'
      AND (SELECT array_agg(o ->> 'value' ORDER BY o ->> 'value')
           FROM jsonb_array_elements(w #> '{widget-data-source,options}') o) = ARRAY['HYBRID', 'OWNER', 'TENANT']) THEN
    RAISE EXCEPTION 'The land ownership summary is not a select of OWNER, TENANT and HYBRID';
  END IF;

  -- Column order of the phone, lands and farm input tables.
  SELECT string_agg(s.section_id, ', ') INTO found
  FROM "public"."g2p_register_sections" s
  JOIN (VALUES
    ('farmer_lands', ARRAY['land_id', 'land_ownership_type', 'land_size', 'unit', 'area_in_hectare', 'soil_fertility',
        'current_land_use', 'farming_type', 'year_of_acquisition', 'means_of_acquisition', 'land_kebele',
        'certificate_storage_id', 'remark']),
    ('farmer_farm_inputs', ARRAY['link_internal_record_id', 'fertilizer_use', 'amount_fertilizer_utilized',
        'pesticide_use', 'amount_pesticide_utilized', 'insecticide_use', 'amount_insecticide_utilized',
        'improved_seed_use', 'amount_improved_seed_utilized', 'water_sources', 'irrigation_type',
        'access_to_machinery', 'machinery_types', 'access_to_finance', 'finance_access_types',
        'livestock_water_sources']),
    ('farmer_farm_inputs_intake', ARRAY['link_internal_record_id', 'fertilizer_use', 'amount_fertilizer_utilized',
        'pesticide_use', 'amount_pesticide_utilized', 'insecticide_use', 'amount_insecticide_utilized',
        'improved_seed_use', 'amount_improved_seed_utilized', 'water_sources', 'irrigation_type',
        'access_to_machinery', 'machinery_types', 'access_to_finance', 'finance_access_types',
        'livestock_water_sources']),
    ('farmer_phones', ARRAY['phone_type', 'phone_number', 'phone_e164', 'country_code', 'is_primary'])
  ) e(section_id, expected) ON e.section_id = s.section_id
  WHERE (SELECT array_agg(c ->> 'column-key' ORDER BY ord)
         FROM jsonb_array_elements(s.section_ui_schema::jsonb #> '{panels,0,panels,0,widgets,0,widget-data-columns}')
              WITH ORDINALITY x(c, ord)) IS DISTINCT FROM e.expected;
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Table columns are not in the agreed order: %', found;
  END IF;

  -- Select columns that read Master Data.
  SELECT string_agg(id, ', ') INTO found FROM (
    SELECT r.section_id || '.' || r.column_key || ' (' || r.list || ')' AS id
    FROM (VALUES
      ('farmer_lands', 'soil_fertility', 'SOIL_FERTILITY'),
      ('farmer_livestock', 'disease_type', 'LIVESTOCK_DISEASE'),
      ('farmer_livestock_intake', 'disease_type', 'LIVESTOCK_DISEASE')) r(section_id, column_key, list)
    WHERE NOT EXISTS (
      SELECT 1 FROM "public"."g2p_register_sections" s,
        jsonb_array_elements(s.section_ui_schema::jsonb #> '{panels,0,panels,0,widgets,0,widget-data-columns}') c
      WHERE s.section_id = r.section_id AND c ->> 'column-key' = r.column_key AND c ->> 'widget' = 'select'
        AND c #>> '{widget-data-source,params,attribute_id}' = r.list
        AND c #>> '{widget-data-source,valueKey}' = 'value_code')) m;
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Table select columns do not read their Master Data list: %', found;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM "public"."g2p_register_sections" s,
      jsonb_array_elements(s.section_ui_schema::jsonb #> '{panels,0,panels,0,widgets,0,widget-data-columns}') c
    WHERE s.section_id = 'farmer_phones' AND c ->> 'column-key' = 'is_primary' AND c ->> 'widget' = 'select') THEN
    RAISE EXCEPTION 'The primary phone column is not a yes/no select';
  END IF;

  -- The household head question is the yes/no radio the other questions use.
  IF NOT EXISTS (
    SELECT 1 FROM "public"."g2p_register_sections" s,
      jsonb_path_query(s.section_ui_schema::jsonb, 'lax $.** ? (@."widget-id" == "is_household_head")') w
    WHERE s.section_id = 'farmer_household_lookup' AND w ->> 'widget' = 'boolean'
      AND w #>> '{widget-data-format,booleanControlType}' = 'radio') THEN
    RAISE EXCEPTION 'The household head question is not a yes/no radio';
  END IF;

  -- The two table dates print in the Ethiopian calendar.
  SELECT string_agg(id, ', ') INTO found FROM (
    SELECT s.section_id || '.' || (c ->> 'column-key') AS id
    FROM "public"."g2p_register_sections" s,
      jsonb_array_elements(s.section_ui_schema::jsonb #> '{panels,0,panels,0,widgets,0,widget-data-columns}') c
    WHERE s.section_id IN ('farmer_crops', 'farmer_crops_intake', 'farmer_livestock', 'farmer_livestock_intake')
      AND c ->> 'column-key' IN ('planted_date', 'collected_date')
      AND (c #>> '{widget-data-format,calendar}' IS DISTINCT FROM 'ethiopian'
           OR c #>> '{widget-data-format,dateFormat}' IS DISTINCT FROM 'DD/MM/YYYY')) m;
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Table dates are not formatted in the Ethiopian calendar: %', found;
  END IF;

  -- Labels staff read.
  SELECT string_agg(t.k, ', ') INTO found FROM (VALUES
    ('phone_number_international', 'Phone number (international)'), ('land_size_unit', 'Land size unit'), ('livestock_sex', 'Sex'),
    ('phone_country_code', 'Phone country (2-letter code)'),
    ('irrigation_water_source', 'Water source for irrigation'),
    ('farm_input_livestock_water_source', 'Livestock water source (farm input)'),
    ('amount_fertilizer_utilized', 'Amount of fertilizer used (kg)'),
    ('amount_pesticide_utilized', 'Amount of pesticide used (litres)'),
    ('amount_insecticide_utilized', 'Amount of insecticide used (litres)'),
    ('amount_improved_seed_utilized', 'Amount of improved seed used (kg)')) t(k, v)
  WHERE NOT EXISTS (SELECT 1 FROM "public"."registry_languages" l
                    WHERE l."is_default" AND l."domain_translation"::jsonb ->> t.k = t.v);
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Table labels do not read as agreed: %', found;
  END IF;
END $$;
