-- G2R-334: repair existing metadata without replacing unrelated columns/options.
-- An empty section stays valid; a saved row needs its type and integer count.
UPDATE "public"."g2p_register_sections" AS section
SET "section_ui_schema" = jsonb_set(
    section.section_ui_schema::jsonb,
    '{panels,0,panels,0,widgets,0,widget-data-columns}',
    (
        SELECT jsonb_agg(
            CASE column_config->>'column-key'
                WHEN 'livestock_type' THEN column_config || '{"widget-required":true}'::jsonb
                WHEN 'head_count' THEN column_config || jsonb_build_object(
                    'widget-required', true,
                    'widget-data-validation',
                    COALESCE(column_config->'widget-data-validation', '{}'::jsonb)
                        || '{"min":0,"max":2147483647}'::jsonb
                )
                ELSE column_config
            END ORDER BY ordinal
        )
        FROM jsonb_array_elements(
            section.section_ui_schema::jsonb #> '{panels,0,panels,0,widgets,0,widget-data-columns}'
        ) WITH ORDINALITY AS columns(column_config, ordinal)
    )
)
WHERE section.section_id = 'farmer_livestock_livestock_details_section_01';
