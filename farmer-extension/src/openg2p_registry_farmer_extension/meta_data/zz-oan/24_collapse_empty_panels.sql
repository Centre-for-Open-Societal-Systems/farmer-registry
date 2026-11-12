-- A panel with no widgets and no child panels only adds blank spacing, so it
-- is dropped from its parent. Panels that hold widgets or other panels stay.
CREATE OR REPLACE FUNCTION pg_temp.oan_collapse_empty_panels(node jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  result jsonb;
BEGIN
  IF jsonb_typeof(node) = 'array' THEN
    SELECT COALESCE(jsonb_agg(pg_temp.oan_collapse_empty_panels(value) ORDER BY ord), '[]'::jsonb)
      INTO result FROM jsonb_array_elements(node) WITH ORDINALITY AS a(value, ord);
  ELSIF jsonb_typeof(node) = 'object' THEN
    SELECT COALESCE(jsonb_object_agg(key, pg_temp.oan_collapse_empty_panels(value)), '{}'::jsonb)
      INTO result FROM jsonb_each(node);
    IF jsonb_typeof(result->'panels') = 'array' THEN
      result := jsonb_set(result, '{panels}', COALESCE((
        SELECT jsonb_agg(p ORDER BY ord)
        FROM jsonb_array_elements(result->'panels') WITH ORDINALITY AS a(p, ord)
        WHERE NOT (jsonb_typeof(p) = 'object' AND p ? 'panel-id'
                   AND COALESCE(jsonb_array_length(p->'widgets'), 0) = 0
                   AND COALESCE(jsonb_array_length(p->'panels'), 0) = 0)
      ), '[]'::jsonb));
    END IF;
  ELSE
    result := node;
  END IF;
  RETURN result;
END $$;

UPDATE public.g2p_register_sections
SET section_ui_schema = pg_temp.oan_collapse_empty_panels(section_ui_schema)
WHERE section_ui_schema IS NOT NULL
  AND section_ui_schema::text LIKE '%"panel-id"%';
