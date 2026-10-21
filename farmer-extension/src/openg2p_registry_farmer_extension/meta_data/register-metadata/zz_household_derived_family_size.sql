-- Family Size is derived by the household domain service from male + female totals.
-- New migration: do not change checksums of already-applied layout seeds.

UPDATE public.g2p_register_sections
SET section_ui_schema = $schema$
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
              "widget-data-format": {
                "minimum": 0,
                "numericType": "integer",
                "thousandSeparator": ","
              },
              "widget-data-validation": {
                "min": 0
              }
            },
            {
              "widget": "number",
              "widget-id": "number_of_female_members",
              "widget-type": "input",
              "widget-label": "number_of_females_in_family",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "9055ab43-c85d-4833-bd00-ca657bb72644.number_of_female_members",
              "widget-data-format": {
                "minimum": 0,
                "numericType": "integer",
                "thousandSeparator": ","
              },
              "widget-data-validation": {
                "min": 0
              }
            },
            {
              "widget": "number",
              "widget-id": "number_of_children",
              "widget-type": "input",
              "widget-label": "number_of_children_in_family",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "9055ab43-c85d-4833-bd00-ca657bb72644.number_of_children",
              "widget-data-format": {
                "minimum": 0,
                "numericType": "integer",
                "thousandSeparator": ","
              },
              "widget-data-validation": {
                "min": 0
              }
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
              "widget": "select",
              "widget-id": "other_land_owner",
              "widget-type": "input",
              "widget-label": "other_land_owner",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "9055ab43-c85d-4833-bd00-ca657bb72644.other_land_owner",
              "widget-data-source": {
                "type": "static",
                "options": [
                  {
                    "label": "YES",
                    "value": true
                  },
                  {
                    "label": "NO",
                    "value": false
                  }
                ]
              }
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

UPDATE public.g2p_register_sections
SET section_ui_schema = $schema$
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
              "widget-data-format": {
                "minimum": 0,
                "numericType": "integer",
                "thousandSeparator": ","
              },
              "widget-data-validation": {
                "min": 0
              }
            },
            {
              "widget": "number",
              "widget-id": "number_of_female_members",
              "widget-type": "input",
              "widget-label": "number_of_females_in_family",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "9055ab43-c85d-4833-bd00-ca657bb72644.number_of_female_members",
              "widget-data-format": {
                "minimum": 0,
                "numericType": "integer",
                "thousandSeparator": ","
              },
              "widget-data-validation": {
                "min": 0
              }
            },
            {
              "widget": "number",
              "widget-id": "number_of_children",
              "widget-type": "input",
              "widget-label": "number_of_children_in_family",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "9055ab43-c85d-4833-bd00-ca657bb72644.number_of_children",
              "widget-data-format": {
                "minimum": 0,
                "numericType": "integer",
                "thousandSeparator": ","
              },
              "widget-data-validation": {
                "min": 0
              }
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
              "widget": "select",
              "widget-id": "other_land_owner",
              "widget-type": "input",
              "widget-label": "other_land_owner",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "9055ab43-c85d-4833-bd00-ca657bb72644.other_land_owner",
              "widget-data-source": {
                "type": "static",
                "options": [
                  {
                    "label": "YES",
                    "value": true
                  },
                  {
                    "label": "NO",
                    "value": false
                  }
                ]
              }
            }
          ],
          "panel-id": "panel_household_parent_and_size",
          "panel-column-span": 1,
          "panel-orientation": "vertical"
        }
      ],
      "panel-id": "panel_household_information",
      "panel-column-span": 3,
      "panel-orientation": "horizontal",
      "panel-distribution": "1-1"
    }
  ],
  "section-id": "household_household_information",
  "section-title": "household_information",
  "section-editable": true,
  "section-column-span": 3
}
$schema$::jsonb
WHERE section_id = 'household_household_household_information_section_01';
