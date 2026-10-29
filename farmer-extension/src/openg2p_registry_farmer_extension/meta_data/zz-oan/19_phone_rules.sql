-- A farmer's phone number is an Ethiopian mobile number: an optional country
-- prefix (+251, 251 or 0) and nine digits starting with 9 or 7, the way
-- register_domain/derived.py reads one (+251 912 345 678, 0912345678 and
-- 912345678 are one number, stored as its nine national digits). The staff UI
-- applies the pattern as typed; the server applies the same string to the
-- national number it stores (widget_rules.py), for every source: web, ODK and
-- partners. The pattern is written once, here, and read by both.
--
-- Rewrites the phone number column of the farmer_phones section by its
-- column key, after 15_sections.sql has built it; running it again changes
-- nothing. Saved numbers are not touched: the rule applies to numbers saved
-- from now on.
CREATE OR REPLACE FUNCTION pg_temp.oan_phone_rule(node jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
  result jsonb;
BEGIN
  IF jsonb_typeof(node) = 'array' THEN
    SELECT COALESCE(jsonb_agg(pg_temp.oan_phone_rule(value) ORDER BY ord), '[]'::jsonb)
      INTO result FROM jsonb_array_elements(node) WITH ORDINALITY AS a(value, ord);
  ELSIF jsonb_typeof(node) = 'object' THEN
    SELECT COALESCE(jsonb_object_agg(key, pg_temp.oan_phone_rule(value)), '{}'::jsonb)
      INTO result FROM jsonb_each(node);
    IF node->>'column-key' = 'phone_number' AND node->>'widget' = 'phone' THEN
      result := jsonb_set(result, '{widget-data-validation}',
        COALESCE(result->'widget-data-validation', '{}'::jsonb) ||
        jsonb_build_object('pattern', $pattern$^(\+251|251|0)?[79][0-9]{8}$$pattern$,
                           'maxLength', 20,
                           'patternMessage', 'phone_ethiopian_mobile'));
    END IF;
  ELSE
    result := node;
  END IF;
  RETURN result;
END $fn$;

UPDATE public.g2p_register_sections
SET section_ui_schema = pg_temp.oan_phone_rule(section_ui_schema)
WHERE section_id = 'farmer_phones' AND section_ui_schema IS NOT NULL;
