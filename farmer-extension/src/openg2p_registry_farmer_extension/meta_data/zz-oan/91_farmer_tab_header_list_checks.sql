-- Checks for the Farmer tab header, the identity and membership fields and the
-- farmer list (05, 11, 12, 20 and 89). Like 90_checks.sql, it raises an error
-- that fails the seed when one of them did not apply.

DO $$
DECLARE
  f constant text := 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';
  found text;
BEGIN
  -- Header: OAN's copy with captions of its own is on the Farmer tab, and
  -- upstream's is detached.
  IF NOT EXISTS (SELECT 1 FROM "public"."g2p_register_sections"
                 WHERE section_id = 'farmer_header' AND section_mnemonic = 'farmer_header'
                   AND section_ui_schema->>'section-id' = 'farmer_header'
                   AND section_ui_schema #>> '{panels,0,panels,0,widgets,0,widget}' = 'header-section'
                   AND section_ui_schema #>> '{panels,0,panels,0,widgets,0,widget-labels,functionalId}' = 'farmer_header_farmer_id') THEN
    RAISE EXCEPTION 'OAN farmer header section is missing or has no captions (11_header_section.sql)';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM "public"."g2p_register_ui_tab_sections"
                 WHERE tab_section_id = 'farmer_farmer_tab__farmer_header' AND tab_id = 'farmer_farmer_tab'
                   AND section_id = 'farmer_header') THEN
    RAISE EXCEPTION 'OAN farmer header is not attached to the Farmer tab (20_layout.sql)';
  END IF;
  IF EXISTS (SELECT 1 FROM "public"."g2p_register_ui_tab_sections"
             WHERE section_id = '01425f4e-720e-4a4e-a0db-73f371ae2a07') THEN
    RAISE EXCEPTION 'Upstream farmer header is still attached next to the OAN header (20_layout.sql)';
  END IF;
  -- The header keeps the photo and name paths of upstream's.
  IF NOT EXISTS (SELECT 1 FROM "public"."g2p_register_sections" h
                 JOIN "public"."g2p_register_sections" u ON u.section_id = '01425f4e-720e-4a4e-a0db-73f371ae2a07'
                 WHERE h.section_id = 'farmer_header'
                   AND h.section_ui_schema #> '{panels,0,panels,0,widgets,0,widget-data-path}'
                     = u.section_ui_schema #> '{panels,0,panels,0,widgets,0,widget-data-path}') THEN
    RAISE EXCEPTION 'OAN farmer header lost the data paths of the upstream header';
  END IF;
  -- Every caption key has text.
  SELECT string_agg(k.key || '=' || k.value, ', ') INTO found
  FROM "public"."g2p_register_sections" s,
       jsonb_each_text(s.section_ui_schema #> '{panels,0,panels,0,widgets,0,widget-labels}') k
  WHERE s.section_id = 'farmer_header'
    AND NOT EXISTS (SELECT 1 FROM "public"."registry_languages" l
                    WHERE l.is_default AND COALESCE(l.domain_translation::jsonb ->> k.value, '') <> '');
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Farmer header captions without text (87_zz_farmer_tab_text.sql): %', found;
  END IF;

  -- List: Farmer ID first, then the three names, then the rest.
  IF (SELECT array_agg(e->>'field_name' ORDER BY (e->>'order')::int)
      FROM "public"."g2p_register_schemas" d, json_array_elements(d.search_result_schema) e
      WHERE d.register_id = f)
     IS DISTINCT FROM ARRAY['functional_record_id', 'first_name', 'middle_name', 'last_name', 'gender', 'birth_date',
                            'marital_status', 'education_level', 'region_name', 'zone_name', 'woreda_name', 'kebele_name'] THEN
    RAISE EXCEPTION 'Farmer list columns are not Farmer ID, names, then the rest (05_registers.sql)';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM "public"."g2p_register_schemas" d, json_array_elements(d.search_result_schema) e
                 WHERE d.register_id = f AND e->>'field_name' = 'middle_name' AND e->>'display_label' = 'Father''s name')
     OR NOT EXISTS (SELECT 1 FROM "public"."g2p_register_schemas" d, json_array_elements(d.search_result_schema) e
                 WHERE d.register_id = f AND e->>'field_name' = 'functional_record_id' AND e->>'display_label' = 'Farmer ID') THEN
    RAISE EXCEPTION 'Farmer list column labels were changed (05_registers.sql)';
  END IF;

  -- Read-only and required settings, by section and widget-id.
  SELECT string_agg(c.section_id || '.' || c.wid, ', ') INTO found
  FROM (VALUES
    ('farmer_identity', 'odk_farmer_id', 'readonly'), ('farmer_identity', 'pula_id', 'readonly'),
    ('farmer_location', 'country_code', 'readonly'),
    ('farmer_personal_details', 'birth_date_ec', 'readonly'),
    ('farmer_membership', 'farmer_cluster_role', 'editable'),
    ('farmer_membership', 'primary_cooperative_name', 'optional'),
    ('farmer_membership', 'cooperative_union_name', 'optional')
  ) c(section_id, wid, want)
  LEFT JOIN "public"."g2p_register_sections" s ON s.section_id = c.section_id
  LEFT JOIN LATERAL (SELECT jsonb_path_query_first(s.section_ui_schema,
                       'lax $.**.widgets[*] ? (@."widget-id" == $id)', jsonb_build_object('id', c.wid)) AS x) q ON true
  WHERE q.x IS NULL
     OR (c.want = 'readonly' AND COALESCE((q.x->>'widget-readonly')::boolean, false) IS NOT TRUE)
     OR (c.want = 'editable' AND COALESCE((q.x->>'widget-readonly')::boolean, false) IS TRUE)
     OR (c.want = 'optional' AND COALESCE((q.x->>'widget-required')::boolean, false) IS TRUE);
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Farmer tab widgets with the wrong read-only or required setting (12_form_sections.sql): %', found;
  END IF;

  -- Fields shown only under a condition carry a show action.
  SELECT string_agg(c.section_id || '.' || c.wid, ', ') INTO found
  FROM (VALUES
    ('farmer_identity', 'rid'), ('farmer_identity', 'foundational_id'), ('farmer_identity', 'odk_farmer_id'),
    ('farmer_identity', 'pula_id'), ('farmer_personal_details', 'birth_date_ec'),
    ('farmer_membership', 'primary_cooperative_name'), ('farmer_membership', 'cooperative_union_name')
  ) c(section_id, wid)
  LEFT JOIN "public"."g2p_register_sections" s ON s.section_id = c.section_id
  WHERE s.section_id IS NULL OR NOT jsonb_path_exists(s.section_ui_schema,
          'lax $.**.widgets[*] ? (@."widget-id" == $id && exists(@."widget-data-options".actions[*] ? (@.action == "show")))',
          jsonb_build_object('id', c.wid));
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Farmer tab widgets shown only under a condition have no show action: %', found;
  END IF;

  -- The two cooperative names are required when their member answer is yes.
  SELECT string_agg(c.wid, ', ') INTO found
  FROM (VALUES ('primary_cooperative_name'), ('cooperative_union_name')) c(wid)
  WHERE NOT EXISTS (SELECT 1 FROM "public"."g2p_register_sections" s
          WHERE s.section_id = 'farmer_membership' AND jsonb_path_exists(s.section_ui_schema,
            'lax $.**.widgets[*] ? (@."widget-id" == $id && exists(@."widget-data-options".actions[*] ? (@.action == "require")))',
            jsonb_build_object('id', c.wid)));
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Cooperative names have no require action: %', found;
  END IF;

  -- The Yes/No questions are radios.
  SELECT string_agg(c.section_id || '.' || c.wid, ', ') INTO found
  FROM (VALUES ('farmer_socio_economic_health', 'disabled'), ('farmer_socio_economic_health', 'is_psnp_user'),
               ('farmer_socio_economic_health', 'is_farmer'), ('farmer_identity', 'has_national_id')) c(section_id, wid)
  WHERE NOT EXISTS (SELECT 1 FROM "public"."g2p_register_sections" s
          WHERE s.section_id = c.section_id AND jsonb_path_exists(s.section_ui_schema,
            'lax $.**.widgets[*] ? (@."widget-id" == $id && @.widget == "boolean" && @."widget-data-format".booleanControlType == "radio")',
            jsonb_build_object('id', c.wid)));
  IF found IS NOT NULL THEN
    RAISE EXCEPTION 'Yes/No questions that are not radios: %', found;
  END IF;
END $$;
