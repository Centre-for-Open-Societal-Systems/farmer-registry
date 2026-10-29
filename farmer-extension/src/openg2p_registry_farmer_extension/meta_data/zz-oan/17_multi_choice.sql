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
  'farmer_farm_inputs', 'farmer_farm_inputs_intake', 'farmer_enumerator');

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
