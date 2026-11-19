-- Format errors in plain words.
--
-- The staff UI shows a field's `patternMessage` exactly as stored: the widget
-- library translates the label, placeholder, help text and tooltip, but not the
-- validation messages. Stored as a translation key (fayda_fin_format, ...), it
-- reached the officer as that key. The server check (widget_rules.py) resolves
-- a key or passes plain text through, so plain text reads the same on both.
--
-- Earlier files (12, 15, 19, 85) set the keys; this one, sorting after them,
-- replaces each key with its short text everywhere in the section schemas. It
-- is idempotent: a second run finds no key left. 90_checks.sql fails the seed if a
-- name or phone field loses its message, and 89_plain_pattern_messages_checks.sql
-- if any patternMessage still looks like a key.

CREATE OR REPLACE FUNCTION pg_temp.oan_plain_pattern_messages(node jsonb, texts jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  result jsonb;
BEGIN
  IF jsonb_typeof(node) = 'array' THEN
    SELECT COALESCE(jsonb_agg(pg_temp.oan_plain_pattern_messages(value, texts) ORDER BY ord), '[]'::jsonb)
      INTO result FROM jsonb_array_elements(node) WITH ORDINALITY AS a(value, ord);
    RETURN result;
  ELSIF jsonb_typeof(node) = 'object' THEN
    SELECT COALESCE(jsonb_object_agg(key,
             CASE WHEN key = 'patternMessage' AND jsonb_typeof(value) = 'string' AND texts ? (value #>> '{}')
                  THEN texts -> (value #>> '{}')
                  ELSE pg_temp.oan_plain_pattern_messages(value, texts) END), '{}'::jsonb)
      INTO result FROM jsonb_each(node);
    RETURN result;
  END IF;
  RETURN node;
END;
$$;

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = pg_temp.oan_plain_pattern_messages("section_ui_schema"::jsonb, '{
  "fayda_fin_format": "Enter a 12-digit FIN or a 16-digit FAN, digits only.",
  "fayda_rid_format": "Enter the 29-digit RID, digits only.",
  "name_letters_only": "Use letters only; spaces, apostrophes and hyphens are allowed.",
  "phone_ethiopian_mobile": "Enter a mobile number such as 0912345678 or +251912345678.",
  "email_format": "Enter an email address such as name@example.org.",
  "country_code_format": "Enter a 2-letter country code, such as ET.",
  "plus_code_format": "Enter a plus code such as 8FVC9G8F+6W."
}'::jsonb)
WHERE "section_ui_schema"::text ~ '"patternMessage": "(fayda_fin_format|fayda_rid_format|name_letters_only|phone_ethiopian_mobile|email_format|country_code_format|plus_code_format)"';
