-- ODK and staff forms preserve every selected answer. These are additive OAN
-- JSON columns; existing singular fields and their history remain unchanged.
-- Native migration creates columns before this metadata seed is applied.
DO $backfill$
DECLARE item record; table_name text;
BEGIN
  FOR item IN SELECT * FROM (VALUES
      ('farmers', 'source_of_income', 'income_sources'),
      ('farm_inputs', 'water_source', 'water_sources'),
      ('farm_inputs', 'livestock_water_source', 'livestock_water_sources'),
      ('farm_inputs', 'machinery_type', 'machinery_types'),
      ('farm_inputs', 'finance_access_type', 'finance_access_types')
    ) fields(suffix, old_field, new_field)
  LOOP
    FOREACH table_name IN ARRAY ARRAY['g2p_register_' || item.suffix,
        'g2p_register_history_' || item.suffix, 'g2p_intake_form_' || item.suffix]
    LOOP
      EXECUTE format('UPDATE %I SET %I = json_build_array(%I) WHERE %I IS NULL AND %I IS NOT NULL AND %I::text <> %L',
          table_name, item.new_field, item.old_field, item.new_field,
          item.old_field, item.old_field, '');
    END LOOP;
  END LOOP;
END $backfill$;

-- Rewrite OAN-owned widget trees only, named by id below. The helper is
-- session-local and never changes upstream metadata or platform code.
-- Conditions use native contains.
CREATE OR REPLACE FUNCTION pg_temp.oan_multi_choice(node jsonb, fields jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $widget$
DECLARE result jsonb; key text; value jsonb; old_field text; new_field text;
BEGIN
  IF jsonb_typeof(node) = 'array' THEN
    SELECT COALESCE(jsonb_agg(pg_temp.oan_multi_choice(v, fields) ORDER BY n), '[]'::jsonb)
      INTO result FROM jsonb_array_elements(node) WITH ORDINALITY a(v,n);
    RETURN result;
  ELSIF jsonb_typeof(node) <> 'object' THEN RETURN node;
  END IF;
  result := '{}'::jsonb;
  FOR key, value IN SELECT * FROM jsonb_each(node) LOOP
    result := result || jsonb_build_object(key, pg_temp.oan_multi_choice(value,fields));
  END LOOP;
  FOR old_field,new_field IN SELECT * FROM jsonb_each_text(fields) LOOP
    IF node->>'widget' = 'select' AND
        (node->>'column-key' = old_field OR node->>'widget-id' = old_field) THEN
      result := jsonb_set(result,'{widget}','"multi-select"'::jsonb);
      FOREACH key IN ARRAY ARRAY['column-key','widget-id','widget-data-path'] LOOP
        IF result ? key THEN
          result := jsonb_set(result,ARRAY[key],to_jsonb(regexp_replace(result->>key,
              old_field || '$',new_field)));
        END IF;
      END LOOP;
      IF result #> '{widget-data-source,params,attribute_id}' IS NOT NULL THEN
        result := jsonb_set(result,'{widget-data-source,valueKey}','"value_code"'::jsonb);
      END IF;
    END IF;
    IF node ? 'field' AND (node->>'field' = old_field OR right(node->>'field',length(old_field)+1) = '.' || old_field) THEN
      result := jsonb_set(result,'{field}',to_jsonb(regexp_replace(node->>'field',old_field || '$',new_field)));
      IF node->>'operator' = 'equals' THEN
        result := jsonb_set(result,'{operator}','"contains"'::jsonb);
      END IF;
    END IF;
  END LOOP;
  RETURN result;
END $widget$;

UPDATE g2p_register_sections SET section_ui_schema = pg_temp.oan_multi_choice(
    section_ui_schema::jsonb,'{"source_of_income":"income_sources","water_source":"water_sources",
    "livestock_water_source":"livestock_water_sources","machinery_type":"machinery_types"}'::jsonb)
WHERE section_id IN (
  'farmer_identity', 'farmer_identity_verification', 'farmer_personal_details',
  'farmer_socio_economic_health', 'farmer_location', 'farmer_photo', 'farmer_phones', 'farmer_documents',
  'farmer_household_lookup', 'household_information', 'farmer_membership', 'farmer_lands',
  'farmer_land_summary', 'farmer_crops', 'farmer_crops_intake', 'farmer_livestock', 'farmer_livestock_intake',
  'farmer_farm_inputs', 'farmer_farm_inputs_intake', 'farmer_enumerator', 'farmer_email');

-- Water questions belong to each repeated crop/animal, not just the holding.
WITH columns(section_id, field, label, attribute_id) AS (VALUES
  ('farmer_crops','water_sources','water_source','WATER_SOURCE'),
  ('farmer_crops_intake','water_sources','water_source','WATER_SOURCE'),
  ('farmer_livestock','water_sources','livestock_water_source','WATER_SOURCE'),
  ('farmer_livestock_intake','water_sources','livestock_water_source','WATER_SOURCE'))
UPDATE g2p_register_sections s SET section_ui_schema=jsonb_set(s.section_ui_schema::jsonb,
    '{panels,0,panels,0,widgets,0,widget-data-columns}',
    (s.section_ui_schema::jsonb #> '{panels,0,panels,0,widgets,0,widget-data-columns}') ||
    jsonb_build_array(jsonb_build_object('widget','multi-select','column-key',c.field,
      'widget-type','input','widget-label',c.label,'widget-readonly',false,'widget-data-path',c.field,
      'widget-data-source',jsonb_build_object('type','api','method','POST','service','attributes',
        'endpoint','values','labelKey','value_display','valueKey','value_code',
        'params',jsonb_build_object('attribute_id',c.attribute_id)))))
FROM columns c WHERE s.section_id=c.section_id AND NOT EXISTS (
  SELECT 1 FROM jsonb_array_elements(s.section_ui_schema::jsonb #> '{panels,0,panels,0,widgets,0,widget-data-columns}') w
  WHERE w->>'column-key'=c.field);

UPDATE g2p_register_sections s SET section_ui_schema=jsonb_set(s.section_ui_schema::jsonb,
    '{panels,0,panels,0,widgets,0,widget-data-columns}',
    (s.section_ui_schema::jsonb #> '{panels,0,panels,0,widgets,0,widget-data-columns}') ||
    '[{"widget":"multi-select","column-key":"finance_access_types","widget-type":"input",
       "widget-label":"finance_access_type","widget-readonly":false,"widget-data-path":"finance_access_types",
       "widget-data-source":{"type":"api","method":"POST","params":{"attribute_id":"FINANCE_ACCESS_TYPE"},
         "service":"attributes","endpoint":"values","labelKey":"value_display","valueKey":"value_code"}}]'::jsonb)
WHERE s.section_id IN ('farmer_farm_inputs','farmer_farm_inputs_intake') AND NOT EXISTS (
  SELECT 1 FROM jsonb_array_elements(s.section_ui_schema::jsonb #> '{panels,0,panels,0,widgets,0,widget-data-columns}') w
  WHERE w->>'column-key'='finance_access_types');

-- Table column order and column wording. This runs after every file that adds
-- or converts a column of these tables (10, 15 and the multi-choice columns
-- above), so the order below is the order staff read. A column that is not
-- listed keeps its place after the listed ones. Display only: no column key,
-- data path or stored value changes.
--
--   farmer_lands        the parcel's Land ID first, then what kind of land and
--                       how big (size, unit, hectares), then its use and history.
--                       Soil fertility reads the SOIL_FERTILITY Master Data list;
--                       rows already hold its codes (SF_HIGH, SF_MEDIUM, SF_LOW).
--   farmer_farm_inputs  each "used" answer is followed by its amount; water,
--                       machinery and finance are grouped. The water source
--                       here is asked about irrigation, and the livestock water
--                       source is also a column of the livestock tables, so the
--                       farm-input one says where it comes from.
CREATE OR REPLACE FUNCTION pg_temp.oan_table_columns(section_ids text[], column_order text[], patches jsonb)
RETURNS void LANGUAGE sql AS $$
  UPDATE "public"."g2p_register_sections" s
  SET "section_ui_schema" = jsonb_set(s."section_ui_schema"::jsonb, '{panels,0,panels,0,widgets,0,widget-data-columns}', (
    SELECT jsonb_agg(CASE WHEN patches ? (c ->> 'column-key') THEN c || (patches -> (c ->> 'column-key')) ELSE c END
                     ORDER BY COALESCE(array_position(column_order, c ->> 'column-key'), 1000 + ord))
    FROM jsonb_array_elements(s."section_ui_schema"::jsonb #> '{panels,0,panels,0,widgets,0,widget-data-columns}')
         WITH ORDINALITY x(c, ord)))
  WHERE s."section_id" = ANY (section_ids)
    AND jsonb_typeof(s."section_ui_schema"::jsonb #> '{panels,0,panels,0,widgets,0,widget-data-columns}') = 'array';
$$;

SELECT pg_temp.oan_table_columns(
  ARRAY['farmer_lands'],
  ARRAY['land_id', 'land_ownership_type', 'land_size', 'unit', 'area_in_hectare', 'soil_fertility',
        'current_land_use', 'farming_type', 'year_of_acquisition', 'means_of_acquisition', 'land_kebele',
        'certificate_storage_id', 'remark'],
  '{"unit": {"widget-label": "land_size_unit"},
    "soil_fertility": {"widget": "select",
      "widget-data-source": {"type": "api", "method": "POST", "params": {"attribute_id": "SOIL_FERTILITY"},
                             "service": "attributes", "endpoint": "values", "labelKey": "value_display", "valueKey": "value_code"}}}'::jsonb);

SELECT pg_temp.oan_table_columns(
  ARRAY['farmer_farm_inputs', 'farmer_farm_inputs_intake'],
  ARRAY['link_internal_record_id', 'fertilizer_use', 'amount_fertilizer_utilized', 'pesticide_use',
        'amount_pesticide_utilized', 'insecticide_use', 'amount_insecticide_utilized', 'improved_seed_use',
        'amount_improved_seed_utilized', 'water_sources', 'irrigation_type', 'access_to_machinery',
        'machinery_types', 'access_to_finance', 'finance_access_types', 'livestock_water_sources'],
  '{"water_sources": {"widget-label": "irrigation_water_source"},
    "livestock_water_sources": {"widget-label": "farm_input_livestock_water_source"}}'::jsonb);
