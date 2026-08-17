-- Farmer phones are modeled as a child register so a farmer can own multiple
-- typed numbers while retaining one authoritative primary number.
INSERT INTO public.g2p_register_definitions (
    register_id, register_mnemonic, register_subject, register_description,
    master_register_id, register_rank, functional_id_generation_required,
    register_purpose, program_id, program_mnemonic, register_icon, has_image,
    dedup_is_enabled, dedup_threshold_score, completion_score_required,
    outgest_applicable, requires_registrant_authentication,
    registrant_authentication_validity_days,
    registrant_re_auth_warning_days_before
) VALUES (
    'c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f',
    'FarmerPhone', 'Farmer Phones', 'Farmer Phone Register',
    'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 12, FALSE,
    'TABLE', NULL, NULL, NULL, FALSE, FALSE, 0, FALSE,
    FALSE, FALSE, 730, 30
)
ON CONFLICT (register_id) DO UPDATE SET
    register_mnemonic = EXCLUDED.register_mnemonic,
    register_subject = EXCLUDED.register_subject,
    register_description = EXCLUDED.register_description,
    master_register_id = EXCLUDED.master_register_id,
    register_rank = EXCLUDED.register_rank,
    register_purpose = EXCLUDED.register_purpose;

INSERT INTO public.g2p_register_schemas (
    register_id, deduplicate_schema, search_result_schema, filter_schema
) VALUES (
    'c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f',
    '[]'::json,
    '[{"field_name":"phone_type","display_label":"Phone Type","order":1},{"field_name":"phone_number","display_label":"Phone Number","order":2},{"field_name":"country_code","display_label":"Country","order":3},{"field_name":"is_primary","display_label":"Primary Phone","order":4}]'::json,
    '[{"field_name":"phone_type","display_label":"Phone Type","filter_type":"dropdown","order":1,"allowed_operators":["eq","in"],"options_source":[{"value":"PRIMARY","label":"PRIMARY"},{"value":"SECONDARY","label":"SECONDARY"},{"value":"OTHER","label":"OTHER"}]},{"field_name":"phone_number","display_label":"Phone Number","filter_type":"text","order":2,"allowed_operators":["eq","contains"]},{"field_name":"country_code","display_label":"Country","filter_type":"text","order":3,"allowed_operators":["eq","contains"]},{"field_name":"is_primary","display_label":"Primary Phone","filter_type":"boolean","order":4,"allowed_operators":["eq"]}]'::json
)
ON CONFLICT (register_id) DO UPDATE SET
    deduplicate_schema = EXCLUDED.deduplicate_schema,
    search_result_schema = EXCLUDED.search_result_schema,
    filter_schema = EXCLUDED.filter_schema;

INSERT INTO public.g2p_register_sections (
    register_id, section_id, section_register_id, is_core_section,
    section_mnemonic, section_description, documents_required,
    no_of_verifications_required, is_list, section_weightage,
    section_ui_schema, cr_auto_approve_for_bene_portal,
    cr_auto_approve_for_agent_portal, cr_auto_approve_for_staff_portal,
    cr_auto_approve_for_partner
) VALUES (
    'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',
    'farmer_farmer_phone_numbers_section_01',
    'c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f',
    FALSE, 'fr_farmer_phone_numbers', 'Farmer phone numbers', FALSE,
    0, TRUE, 10,
    $schema$
    {
      "panels": [
        {
          "panels": [
            {
              "widgets": [
                {
                  "widget": "table",
                  "widget-id": "farmer_phone_numbers_table",
                  "widget-type": "table",
                  "widget-label": "farmer_phone_numbers",
                  "widget-readonly": false,
                  "widget-data-path": "c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f.records",
                  "widget-data-columns": [
                    {
                      "widget": "select",
                      "column-key": "phone_type",
                      "widget-type": "input",
                      "widget-label": "phone_type",
                      "widget-readonly": false,
                      "widget-required": true,
                      "widget-data-path": "phone_type",
                      "widget-data-source": {
                        "type": "static",
                        "options": [
                          {"label": "PRIMARY", "value": "PRIMARY"},
                          {"label": "SECONDARY", "value": "SECONDARY"},
                          {"label": "OTHER", "value": "OTHER"}
                        ]
                      }
                    },
                    {
                      "widget": "text",
                      "column-key": "phone_number",
                      "widget-type": "input",
                      "widget-label": "phone_number",
                      "widget-readonly": false,
                      "widget-required": true,
                      "widget-data-path": "phone_number"
                    },
                    {
                      "widget": "text",
                      "column-key": "country_code",
                      "widget-type": "input",
                      "widget-label": "country_code",
                      "widget-readonly": false,
                      "widget-required": false,
                      "widget-data-path": "country_code",
                      "default": "ETH"
                    },
                    {
                      "widget": "checkbox",
                      "column-key": "is_primary",
                      "widget-type": "input",
                      "widget-label": "is_primary_phone",
                      "widget-readonly": false,
                      "widget-required": false,
                      "widget-data-path": "is_primary"
                    }
                  ],
                  "widget-data-add-label": "add_phone",
                  "widget-data-operations": {"add": true, "edit": true, "remove": true}
                }
              ],
              "panel-id": "vertical_panel_farmer_phones",
              "panel-column-span": 3,
              "panel-orientation": "vertical"
            }
          ],
          "panel-id": "horizontal_panel_farmer_phones",
          "panel-orientation": "horizontal"
        }
      ],
      "section-id": "farmer_phone_numbers",
      "section-title": "farmer_phone_numbers",
      "section-editable": true
    }
    $schema$::jsonb,
    FALSE, FALSE, FALSE, FALSE
)
ON CONFLICT (section_id) DO UPDATE SET
    section_register_id = EXCLUDED.section_register_id,
    is_list = EXCLUDED.is_list,
    section_description = EXCLUDED.section_description,
    section_ui_schema = EXCLUDED.section_ui_schema;

INSERT INTO public.g2p_register_ui_tab_sections (
    tab_section_id, register_id, tab_id, section_id, section_order
) VALUES (
    'farmer-phone-register-tab-section-01',
    'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',
    'farmer_farmer_tab', 'farmer_farmer_phone_numbers_section_01', 12
)
ON CONFLICT (tab_section_id) DO UPDATE SET
    register_id = EXCLUDED.register_id,
    tab_id = EXCLUDED.tab_id,
    section_id = EXCLUDED.section_id,
    section_order = EXCLUDED.section_order;

INSERT INTO public.g2p_intake_form_ui_tab_sections (
    tab_section_id, tab_id, section_id, section_order
) VALUES (
    'farmer-phone-intake-tab-section-01',
    'a1a4d25a-1cd4-4356-abac-72482721',
    'farmer_farmer_phone_numbers_section_01', 22
)
ON CONFLICT (tab_section_id) DO UPDATE SET
    tab_id = EXCLUDED.tab_id,
    section_id = EXCLUDED.section_id,
    section_order = EXCLUDED.section_order;
