-- Reuse the Household register as the single source of truth while exposing
-- its requested family fields on the Farmer Household tab and Farmer intake.
UPDATE public.g2p_register_sections
SET section_description = 'Household information linked to this farmer',
    section_ui_schema = $schema$
{
  "panels": [
    {
      "panels": [
        {
          "widgets": [
            {
              "widget": "number",
              "widget-id": "number_of_male_members",
              "widget-type": "input",
              "widget-label": "number_of_males_in_family",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "9055ab43-c85d-4833-bd00-ca657bb72644.number_of_male_members",
              "widget-data-format": {"minimum": 0, "numericType": "integer", "thousandSeparator": ","},
              "widget-data-validation": {"min": 0}
            },
            {
              "widget": "number",
              "widget-id": "number_of_female_members",
              "widget-type": "input",
              "widget-label": "number_of_females_in_family",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "9055ab43-c85d-4833-bd00-ca657bb72644.number_of_female_members",
              "widget-data-format": {"minimum": 0, "numericType": "integer", "thousandSeparator": ","},
              "widget-data-validation": {"min": 0}
            },
            {
              "widget": "number",
              "widget-id": "number_of_children",
              "widget-type": "input",
              "widget-label": "number_of_children_in_family",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "9055ab43-c85d-4833-bd00-ca657bb72644.number_of_children",
              "widget-data-format": {"minimum": 0, "numericType": "integer", "thousandSeparator": ","},
              "widget-data-validation": {"min": 0}
            }
          ],
          "panel-id": "panel_household_member_counts",
          "panel-column-span": 1,
          "panel-orientation": "vertical"
        },
        {
          "widgets": [
            {
              "widget": "checkbox",
              "widget-id": "father_included",
              "widget-type": "input",
              "widget-label": "father_included",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "9055ab43-c85d-4833-bd00-ca657bb72644.father_included"
            },
            {
              "widget": "checkbox",
              "widget-id": "mother_included",
              "widget-type": "input",
              "widget-label": "mother_included",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "9055ab43-c85d-4833-bd00-ca657bb72644.mother_included"
            },
            {
              "widget": "number",
              "widget-id": "size_of_group",
              "widget-type": "input",
              "widget-label": "family_size",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "9055ab43-c85d-4833-bd00-ca657bb72644.size_of_group",
              "widget-data-format": {"minimum": 0, "numericType": "integer", "thousandSeparator": ","},
              "widget-data-validation": {"min": 0}
            }
          ],
          "panel-id": "panel_household_parent_and_size",
          "panel-column-span": 1,
          "panel-orientation": "vertical"
        }
      ],
      "panel-id": "panel_farmer_household_information",
      "panel-column-span": 3,
      "panel-orientation": "horizontal",
      "panel-distribution": "1-1"
    }
  ],
  "section-id": "farmer_household_information",
  "section-title": "household_information",
  "section-editable": true,
  "section-column-span": 3
}
$schema$::jsonb
WHERE section_id = 'farmer_household_household_information_section_01';

-- The native Household page/intake uses the same fields, without the Farmer
-- link visibility condition because the Household is the current record.
UPDATE public.g2p_register_sections
SET section_ui_schema = $schema$
{
  "panels": [
    {
      "panels": [
        {
          "widgets": [
            {"widget":"number","widget-id":"number_of_male_members","widget-type":"input","widget-label":"number_of_males_in_family","widget-readonly":false,"widget-required":false,"widget-data-path":"9055ab43-c85d-4833-bd00-ca657bb72644.number_of_male_members","widget-data-format":{"minimum":0,"numericType":"integer","thousandSeparator":","},"widget-data-validation":{"min":0}},
            {"widget":"number","widget-id":"number_of_female_members","widget-type":"input","widget-label":"number_of_females_in_family","widget-readonly":false,"widget-required":false,"widget-data-path":"9055ab43-c85d-4833-bd00-ca657bb72644.number_of_female_members","widget-data-format":{"minimum":0,"numericType":"integer","thousandSeparator":","},"widget-data-validation":{"min":0}},
            {"widget":"number","widget-id":"number_of_children","widget-type":"input","widget-label":"number_of_children_in_family","widget-readonly":false,"widget-required":false,"widget-data-path":"9055ab43-c85d-4833-bd00-ca657bb72644.number_of_children","widget-data-format":{"minimum":0,"numericType":"integer","thousandSeparator":","},"widget-data-validation":{"min":0}}
          ],
          "panel-id":"panel_household_member_counts",
          "panel-column-span":1,
          "panel-orientation":"vertical"
        },
        {
          "widgets": [
            {"widget":"checkbox","widget-id":"father_included","widget-type":"input","widget-label":"father_included","widget-readonly":false,"widget-required":false,"widget-data-path":"9055ab43-c85d-4833-bd00-ca657bb72644.father_included"},
            {"widget":"checkbox","widget-id":"mother_included","widget-type":"input","widget-label":"mother_included","widget-readonly":false,"widget-required":false,"widget-data-path":"9055ab43-c85d-4833-bd00-ca657bb72644.mother_included"},
            {"widget":"number","widget-id":"size_of_group","widget-type":"input","widget-label":"family_size","widget-readonly":false,"widget-required":false,"widget-data-path":"9055ab43-c85d-4833-bd00-ca657bb72644.size_of_group","widget-data-format":{"minimum":0,"numericType":"integer","thousandSeparator":","},"widget-data-validation":{"min":0}}
          ],
          "panel-id":"panel_household_parent_and_size",
          "panel-column-span":1,
          "panel-orientation":"vertical"
        }
      ],
      "panel-id":"panel_household_information",
      "panel-column-span":3,
      "panel-orientation":"horizontal",
      "panel-distribution":"1-1"
    }
  ],
  "section-id":"household_household_information",
  "section-title":"household_information",
  "section-editable":true,
  "section-column-span":3
}
$schema$::jsonb
WHERE section_id = 'household_household_household_information_section_01';

INSERT INTO public.g2p_register_ui_tab_sections (
    tab_section_id, register_id, tab_id, section_id, section_order
) VALUES (
    'farmer-household-information-tab-section-01',
    'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',
    'farmer_household_link_tab',
    'farmer_household_household_information_section_01', 10
)
ON CONFLICT (tab_section_id) DO UPDATE SET
    register_id = EXCLUDED.register_id,
    tab_id = EXCLUDED.tab_id,
    section_id = EXCLUDED.section_id,
    section_order = EXCLUDED.section_order;

INSERT INTO public.g2p_intake_form_ui_tab_sections (
    tab_section_id, tab_id, section_id, section_order
) VALUES (
    'farmer-household-information-intake-section-01',
    'a1a4d25a-1cd4-4356-abac-72482721',
    'farmer_household_household_information_section_01', 12
)
ON CONFLICT (tab_section_id) DO UPDATE SET
    tab_id = EXCLUDED.tab_id,
    section_id = EXCLUDED.section_id,
    section_order = EXCLUDED.section_order;
