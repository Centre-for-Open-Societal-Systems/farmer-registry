-- Fails the seed when text staff read looks like a code.
--
-- Covers every section a tab or an intake form shows: each label, placeholder,
-- help text, section title, validation message and choice is resolved the way
-- the staff UI resolves it (the language's domain translation, then core's,
-- else the string itself) and must not hold an underscore or be an
-- ALL-CAPS code. The document slots (identity_document_1 and the like) are
-- storage keys that the documents widget never shows; its title is checked
-- instead. The search and filter schemas get the same test.

DO $$
DECLARE
  found text;
BEGIN
  SELECT string_agg(DISTINCT s.section_id || ': ' || v.txt, '; ') INTO found
  FROM "public"."g2p_register_sections" s
  CROSS JOIN LATERAL jsonb_path_query(s.section_ui_schema, 'strict $.**') n
  CROSS JOIN LATERAL jsonb_each_text(
    CASE WHEN jsonb_typeof(n) = 'object' THEN n ELSE '{}'::jsonb END) kv
  CROSS JOIN LATERAL (
    SELECT COALESCE(NULLIF(l."domain_translation"::jsonb ->> kv.value, ''),
                    NULLIF(l."core_translation"::jsonb ->> kv.value, ''), kv.value) AS txt
    FROM "public"."registry_languages" l WHERE l."is_default") v
  WHERE (s.section_id IN (SELECT section_id FROM "public"."g2p_register_ui_tab_sections")
         OR s.section_id IN (SELECT section_id FROM "public"."g2p_intake_form_ui_tab_sections"))
    AND kv.key IN ('widget-label', 'widget-data-placeholder', 'widget-data-helptext', 'widget-data-add-label',
                   'section-title', 'panel-title', 'patternMessage', 'minMessage', 'label', 'title',
                   'action_label', 'search_placeholder', 'select_record_label')
    AND kv.value !~ '^[a-z]+(_[a-z]+)*_document_[1-5]$'
    AND v.txt <> 'DD/MM/YYYY'
    AND (v.txt ~ '_' OR v.txt ~ '^[A-Z][A-Z0-9 /-]{3,}$');
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Text staff read looks like a code: %', found;
  END IF;

  SELECT string_agg(DISTINCT d.register_id || ': ' || x, '; ') INTO found
  FROM "public"."g2p_register_schemas" d
  CROSS JOIN LATERAL (
    SELECT jsonb_path_query(COALESCE(d.search_result_schema::jsonb, 'null'::jsonb), 'lax $[*].display_label') #>> '{}' AS x
    UNION ALL
    SELECT jsonb_path_query(COALESCE(d.filter_schema::jsonb, 'null'::jsonb), 'lax $[*].display_label') #>> '{}'
    UNION ALL
    SELECT jsonb_path_query(COALESCE(d.filter_schema::jsonb, 'null'::jsonb), 'lax $[*].options_source[*].label') #>> '{}'
  ) t
  WHERE x ~ '_' OR x ~ '^[A-Z][A-Z0-9 /-]{3,}$';
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'A search or filter label looks like a code: %', found;
  END IF;

  IF EXISTS (SELECT 1 FROM "public"."g2p_register_definitions" r
             WHERE r."register_description" ~ '(register description|_)') THEN
    RAISE EXCEPTION 'A register description is a placeholder or a code';
  END IF;
END $$;
