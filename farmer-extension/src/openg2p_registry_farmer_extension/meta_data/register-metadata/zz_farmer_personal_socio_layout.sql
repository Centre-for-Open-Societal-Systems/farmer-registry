-- Phase 1 Farmer detail/intake layout. These section definitions are shared by
-- Registry View and the Farmer intake form, so both experiences remain aligned.
UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = $schema$
{
  "panels": [
    {
      "panels": [
        {
          "panels": [
            {
              "widgets": [{"widget": "text", "widget-id": "first_name", "widget-type": "input", "widget-label": "first_name_english", "widget-required": false, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.first_name"}],
              "panel-id": "panel_english_first_name",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            },
            {
              "widgets": [{"widget": "text", "widget-id": "middle_name", "widget-type": "input", "widget-label": "middle_name_english", "widget-required": false, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.middle_name"}],
              "panel-id": "panel_english_middle_name",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            },
            {
              "widgets": [{"widget": "text", "widget-id": "last_name", "widget-type": "input", "widget-label": "last_name_english", "widget-required": false, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.last_name"}],
              "panel-id": "panel_english_last_name",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            }
          ],
          "panel-id": "panel_names_english_row",
          "panel-title": "names_english",
          "panel-orientation": "horizontal"
        },
        {
          "panels": [
            {
              "widgets": [{"widget": "text", "widget-id": "first_name_amh", "widget-type": "input", "widget-label": "first_name_amharic", "widget-required": false, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.first_name_amh"}],
              "panel-id": "panel_amharic_first_name",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            },
            {
              "widgets": [{"widget": "text", "widget-id": "middle_name_amh", "widget-type": "input", "widget-label": "middle_name_amharic", "widget-required": false, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.middle_name_amh"}],
              "panel-id": "panel_amharic_middle_name",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            },
            {
              "widgets": [{"widget": "text", "widget-id": "last_name_amh", "widget-type": "input", "widget-label": "last_name_amharic", "widget-required": false, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.last_name_amh"}],
              "panel-id": "panel_amharic_last_name",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            }
          ],
          "panel-id": "panel_names_amharic_row",
          "panel-title": "names_amharic",
          "panel-orientation": "horizontal"
        },
        {
          "panels": [
            {
              "widgets": [{"widget": "text", "widget-id": "first_name_om", "widget-type": "input", "widget-label": "first_name_afaan_oromo", "widget-required": false, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.first_name_om"}],
              "panel-id": "panel_oromo_first_name",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            },
            {
              "widgets": [{"widget": "text", "widget-id": "middle_name_om", "widget-type": "input", "widget-label": "middle_name_afaan_oromo", "widget-required": false, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.middle_name_om"}],
              "panel-id": "panel_oromo_middle_name",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            },
            {
              "widgets": [{"widget": "text", "widget-id": "last_name_om", "widget-type": "input", "widget-label": "last_name_afaan_oromo", "widget-required": false, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.last_name_om"}],
              "panel-id": "panel_oromo_last_name",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            }
          ],
          "panel-id": "panel_names_oromo_row",
          "panel-title": "names_afaan_oromo",
          "panel-orientation": "horizontal"
        },
        {
          "panels": [
            {
              "widgets": [
                {
                  "widget": "select",
                  "widget-id": "gender",
                  "widget-type": "input",
                  "widget-label": "gender",
                  "widget-required": false,
                  "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.gender",
                  "widget-data-source": {"type": "static", "options": [{"label": "MALE", "value": "MALE"}, {"label": "FEMALE", "value": "FEMALE"}, {"label": "OTHERS", "value": "OTHERS"}, {"label": "UNKNOWN", "value": "UNKNOWN"}]}
                }
              ],
              "panel-id": "panel_gender",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            }
          ],
          "panel-id": "panel_personal_demographics_row",
          "panel-orientation": "horizontal"
        }
      ],
      "panel-id": "panel_personal_information_rows",
      "panel-orientation": "vertical"
    }
  ],
  "section-id": "farmer_personal_information",
  "section-title": "farmer_personal_information",
  "section-editable": true,
  "section-column-span": 3
}
$schema$::json
WHERE "section_id" = 'farmer_farmer_personal_identification_section_01';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = $schema$
{
  "panels": [
    {
      "panels": [
        {
          "widgets": [
            {
              "widget": "checkbox",
              "widget-id": "is_household_head",
              "widget-type": "input",
              "widget-label": "is_household_head",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.is_household_head"
            },
            {
              "widget": "select",
              "widget-id": "source_of_income",
              "widget-type": "input",
              "widget-label": "household_income",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.source_of_income",
              "widget-data-source": {"type": "static", "options": [{"label": "CROP_PRODUCTION", "value": "CROP_PRODUCTION"}, {"label": "LIVESTOCK_PRODUCTION", "value": "LIVESTOCK_PRODUCTION"}, {"label": "GOVERNMENT_NGO_SUPPORT", "value": "GOVERNMENT_NGO_SUPPORT"}, {"label": "OTHERS", "value": "OTHERS"}]}
            },
            {
              "widget": "text",
              "widget-id": "source_of_income_other",
              "widget-type": "input",
              "widget-label": "source_of_income_other",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.source_of_income_other",
              "widget-data-options": {"action": "show", "condition": {"field": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.source_of_income", "operator": "equals", "value": "OTHERS"}}
            },
            {
              "widget": "select",
              "widget-id": "education_level",
              "widget-type": "input",
              "widget-label": "education_level",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.education_level",
              "widget-data-source": {"type": "static", "options": [{"label": "ILLITERATE", "value": "ILLITERATE"}, {"label": "CAN_READ_AND_WRITE", "value": "CAN_READ_AND_WRITE"}, {"label": "BASIC", "value": "BASIC"}, {"label": "INTERMEDIARY", "value": "INTERMEDIARY"}, {"label": "HIGHER_EDUCATION", "value": "HIGHER_EDUCATION"}]}
            },
            {
              "widget": "select",
              "widget-id": "marital_status",
              "widget-type": "input",
              "widget-label": "marital_status",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.marital_status",
              "widget-data-source": {"type": "static", "options": [{"label": "SINGLE", "value": "SINGLE"}, {"label": "MARRIED", "value": "MARRIED"}, {"label": "DIVORCED", "value": "DIVORCED"}, {"label": "WIDOWED", "value": "WIDOWED"}, {"label": "SEPARATED", "value": "SEPARATED"}, {"label": "UNKNOWN", "value": "UNKNOWN"}]}
            },
            {
              "widget": "checkbox",
              "widget-id": "is_psnp_user",
              "widget-type": "input",
              "widget-label": "is_psnp_user",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.is_psnp_user"
            }
          ],
          "panel-id": "panel_social_economic_data",
          "panel-title": "socio_economic_details",
          "panel-column-span": 2,
          "panel-orientation": "vertical"
        },
        {
          "widgets": [
            {
              "widget": "checkbox",
              "widget-id": "disabled",
              "widget-type": "input",
              "widget-label": "disabled",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.disabled"
            },
            {
              "widget": "select",
              "widget-id": "disability_type",
              "widget-type": "input",
              "widget-label": "disability_type",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.disability_type",
              "widget-data-source": {"type": "static", "options": [{"label": "VISION", "value": "VISION"}, {"label": "HEARING", "value": "HEARING"}, {"label": "MOBILITY", "value": "MOBILITY"}, {"label": "COGNITION", "value": "COGNITION"}, {"label": "SELF_CARE", "value": "SELF_CARE"}, {"label": "COMMUNICATION", "value": "COMMUNICATION"}]},
              "widget-data-options": {"action": "show", "condition": {"field": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.disabled", "operator": "equals", "value": true}}
            },
            {
              "widget": "select",
              "widget-id": "disability_severity",
              "widget-type": "input",
              "widget-label": "disability_severity",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.disability_severity",
              "widget-data-source": {"type": "static", "options": [{"label": "NO_DIFFICULTY", "value": "NO_DIFFICULTY"}, {"label": "SOME_DIFFICULTY", "value": "SOME_DIFFICULTY"}, {"label": "A_LOT_OF_DIFFICULTY", "value": "A_LOT_OF_DIFFICULTY"}, {"label": "CANNOT_DO_AT_ALL", "value": "CANNOT_DO_AT_ALL"}]},
              "widget-data-options": {"action": "show", "condition": {"field": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.disabled", "operator": "equals", "value": true}}
            }
          ],
          "panel-id": "panel_health_details",
          "panel-title": "health_details",
          "panel-column-span": 1,
          "panel-orientation": "vertical"
        }
      ],
      "panel-id": "panel_socio_economic_and_health",
      "panel-orientation": "horizontal"
    }
  ],
  "section-id": "farmer_socio_economic_and_health",
  "section-title": "farmer_socio_economic_and_health",
  "section-editable": true,
  "section-column-span": 3,
  "section-supporting-documents": []
}
$schema$::json
WHERE "section_id" = 'farmer_farmer_socio_economic_and_health_section_04';
