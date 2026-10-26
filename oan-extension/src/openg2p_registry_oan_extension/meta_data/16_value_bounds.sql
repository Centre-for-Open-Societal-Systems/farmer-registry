-- UI mirrors the domain rules; current-year enforcement is recalculated on
-- every server validation, including imports and submissions with no browser.
CREATE OR REPLACE FUNCTION pg_temp.oan_value_bounds(node jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  result jsonb;
BEGIN
  IF jsonb_typeof(node) = 'array' THEN
    SELECT COALESCE(jsonb_agg(pg_temp.oan_value_bounds(value) ORDER BY ord), '[]'::jsonb)
      INTO result FROM jsonb_array_elements(node) WITH ORDINALITY AS a(value, ord);
  ELSIF jsonb_typeof(node) = 'object' THEN
    SELECT COALESCE(jsonb_object_agg(key, pg_temp.oan_value_bounds(value)), '{}'::jsonb)
      INTO result FROM jsonb_each(node);
    -- Core validates value_code. OAN's strings use that same contract for the
    -- five inherited id-bound selects; no register records are rewritten here.
    IF node->>'widget' = 'select'
       AND node #>> '{widget-data-source,service}' = 'attributes'
       AND node #>> '{widget-data-source,valueKey}' = 'value_id' THEN
      result := jsonb_set(result, '{widget-data-source,valueKey}', '"value_code"'::jsonb);
    END IF;
    IF COALESCE(node->>'column-key', node->>'widget-id') = 'year_of_acquisition' THEN
      result := jsonb_set(result, '{widget-data-validation}',
        COALESCE(result->'widget-data-validation', '{}'::jsonb) ||
        jsonb_build_object('min', 1900, 'max', EXTRACT(YEAR FROM CURRENT_DATE)::integer));
    ELSIF COALESCE(node->>'column-key', node->>'widget-id') = 'collected_date' THEN
      result := jsonb_set(result, '{widget-data-format}',
        COALESCE(result->'widget-data-format', '{}'::jsonb) || '{"dateConstraint":"past-only"}'::jsonb);
    END IF;
  ELSE
    result := node;
  END IF;
  RETURN result;
END $$;

UPDATE public.g2p_register_sections
SET section_ui_schema = pg_temp.oan_value_bounds(section_ui_schema)
WHERE section_ui_schema IS NOT NULL;
