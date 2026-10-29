-- Flags text staff read that looks like a code.
--
-- This is advisory at run time: the db-seed entrypoint does not stop on a
-- failed statement, so a RAISE EXCEPTION here is only logged. The metadata
-- replay in ci/validation/check_native_metadata.py runs every file with
-- ON_ERROR_STOP=1, so there it fails the build.
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


-- The platform screen text overridden in 86_readable_screen_text.sql stays in
-- sentence case, the codes staff see in lists and dropdowns have display text,
-- and the land lookups no longer say "Parent".
DO $$
DECLARE
  found text;
BEGIN
  SELECT string_agg(k.key || '=' || k.value, '; ') INTO found
  FROM "public"."registry_languages" l
  CROSS JOIN LATERAL jsonb_each_text(l."core_translation"::jsonb) k
  WHERE l."is_default"
    AND k.key IN (
    'access_denied',
    'application_reference',
    'approval_status',
    'approved_at',
    'approved_by',
    'assignee_name',
    'attached_documents',
    'change_request',
    'change_requests',
    'tasks_cr',
    'clear_all',
    'completed_at',
    'cr_possible_duplicates',
    'create_new_submission',
    'created_at',
    'created_by',
    'credential_type',
    'decision_action',
    'dedup_result_id',
    'document_icon_alt',
    'draft_submissions',
    'edit_image',
    'enriched_message',
    'export_again',
    'export_history',
    'export_records',
    'finalised_at',
    'form_details',
    'form_status',
    'form_submissions',
    'go_back',
    'import_file',
    'import_successful',
    'incoming_messages',
    'tasks_intake',
    'intake_forms',
    'intake_possible_duplicates',
    'know_more',
    'last_approved_by',
    'last_updated_by',
    'match_score',
    'my_profile',
    'approval_tasks',
    'new_and_old_values',
    'new_intake',
    'no_change_request',
    'no_tab_section',
    'no_version_history',
    'outgoing_messages',
    'pending_requests',
    'pending_submissions',
    'raw_message',
    'record_access_denied',
    'register_possible_duplicates',
    'retry_export',
    'search_change_requests',
    'search_form_submissions',
    'search_messages',
    'search_approval_tasks',
    'search_registers',
    'select_date',
    'select_operator',
    'select_section',
    'select_version',
    'export_start',
    'total_versions',
    'transformed_message',
    'updated_at',
    'upload_file',
    'verification_result',
    'verify_credential',
    'version_history',
    'view_less',
    'view_more',
    'view_queue',
    'register_form_submissions',
    'register_intake_form',
    'kind',
    'registryGen2'
    )
    AND k.value ~ '[^ ] [A-Z][a-z]';
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Platform screen text is in Title Case: %', found;
  END IF;

  SELECT string_agg(c, ', ') INTO found
  FROM unnest(ARRAY['MALE', 'FEMALE', 'SINGLE', 'MARRIED', 'DIVORCED', 'WIDOWED', 'SEPARATED', 'NEVER_ATTEND',
                    'PRIMARY', 'SECONDARY', 'TERTIARY', 'HIGHER_EDUCATION', 'MR', 'MRS', 'MS', 'DR', 'MISS',
                    'NON_FORMAL', 'DRAFT', 'FINAL', 'REJECTED', 'STAFF_PORTAL']) c
  WHERE NOT EXISTS (SELECT 1 FROM "public"."registry_languages" l
                    WHERE l."is_default" AND COALESCE(NULLIF(l."domain_translation"::jsonb ->> c, ''), '') <> '');
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Codes staff read have no display text: %', found;
  END IF;

  SELECT string_agg(s.section_id, ', ') INTO found
  FROM "public"."g2p_register_sections" s
  WHERE s.section_ui_schema::text ~ '"(widget-label|search_placeholder|select_record_label)": "(Parent|Search parent[.]*|Select [Pp]arent)"';
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'A land lookup still says Parent: %', found;
  END IF;

  SELECT string_agg(s.section_id, ', ') INTO found
  FROM "public"."g2p_register_sections" s
  WHERE s.section_ui_schema::text ~ '"attribute_id": "(PREFIX|RELATIONSHIP_TO_HEAD)"[^{}]*\}[^{}]*"labelKey": "value_code"'
     OR s.section_ui_schema::text ~ '"labelKey": "value_code"[^{}]*"params": \{"attribute_id": "(PREFIX|RELATIONSHIP_TO_HEAD)"';
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'A select shows the stored code instead of its display text: %', found;
  END IF;
END $$;
