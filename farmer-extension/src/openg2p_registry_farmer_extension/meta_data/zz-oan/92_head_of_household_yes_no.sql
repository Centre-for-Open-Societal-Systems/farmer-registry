-- "Head of household" in the household members tables reads Yes or No.
--
-- The column is a boolean widget with booleanRepresentation "yes-no". The
-- members table (dialog-table) shows a cell through its widget only for a
-- select; any other value is printed as it is, so the column read "true" and
-- "false" on the Household tab and the farmer form. A select with the static
-- options Yes (true) and No (false) is shown by its option label, and saves the
-- option's own value, so the stored answer stays a boolean and the conditions
-- on it (relationship to the head) are unchanged. Unset is not offered, as
-- before (allowUnset false, default false).
--
-- Only the is_head column of the two members tables changes; its key, label,
-- help text, default and data path stay as they are. Idempotent.
CREATE OR REPLACE FUNCTION pg_temp.oan_head_yes_no(node jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  result jsonb;
BEGIN
  IF jsonb_typeof(node) = 'array' THEN
    SELECT COALESCE(jsonb_agg(pg_temp.oan_head_yes_no(value) ORDER BY ord), '[]'::jsonb)
      INTO result FROM jsonb_array_elements(node) WITH ORDINALITY AS a(value, ord);
  ELSIF jsonb_typeof(node) = 'object' THEN
    SELECT COALESCE(jsonb_object_agg(key, pg_temp.oan_head_yes_no(value)), '{}'::jsonb)
      INTO result FROM jsonb_each(node);
    IF node->>'column-key' = 'is_head' AND node->>'widget' = 'boolean' THEN
      result := (result - 'widget-data-format')
        || '{"widget": "select",
             "widget-data-source": {"type": "static", "options": [
               {"label": "YES", "value": true}, {"label": "NO", "value": false}]}}'::jsonb;
    END IF;
  ELSE
    result := node;
  END IF;
  RETURN result;
END $$;

UPDATE public.g2p_register_sections
SET section_ui_schema = pg_temp.oan_head_yes_no(section_ui_schema)
WHERE section_id IN ('farmer_household_household_member_section_02', 'household_household_household_member_section_02')
  AND section_ui_schema::text LIKE '%"column-key": "is_head"%';
