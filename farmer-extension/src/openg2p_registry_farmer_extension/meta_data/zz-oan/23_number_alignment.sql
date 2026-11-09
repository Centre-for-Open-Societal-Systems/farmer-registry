-- One number rule for every registry screen: numbers are right-aligned and
-- grouped with ",". The age fields that had no format get an integer format.
-- Decimals keep the places and separator they already declare.
CREATE OR REPLACE FUNCTION pg_temp.oan_number_format(node jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  result jsonb;
  fmt jsonb;
BEGIN
  IF jsonb_typeof(node) = 'array' THEN
    SELECT COALESCE(jsonb_agg(pg_temp.oan_number_format(value) ORDER BY ord), '[]'::jsonb)
      INTO result FROM jsonb_array_elements(node) WITH ORDINALITY AS a(value, ord);
  ELSIF jsonb_typeof(node) = 'object' THEN
    SELECT COALESCE(jsonb_object_agg(key, pg_temp.oan_number_format(value)), '{}'::jsonb)
      INTO result FROM jsonb_each(node);
    IF node->>'widget' = 'number' THEN
      fmt := COALESCE(node->'widget-data-format', '{}'::jsonb);
      IF node->>'widget-id' = 'estimated_age' AND NOT (fmt ? 'numericType') THEN
        fmt := fmt || '{"numericType":"integer","minimum":0}'::jsonb;
      END IF;
      fmt := fmt || '{"textAlign":"right","thousandSeparator":","}'::jsonb;
      result := jsonb_set(result, '{widget-data-format}', fmt);
    END IF;
  ELSE
    result := node;
  END IF;
  RETURN result;
END $$;

UPDATE public.g2p_register_sections
SET section_ui_schema = pg_temp.oan_number_format(section_ui_schema)
WHERE section_ui_schema IS NOT NULL
  AND section_ui_schema::text LIKE '%"widget": "number"%';
