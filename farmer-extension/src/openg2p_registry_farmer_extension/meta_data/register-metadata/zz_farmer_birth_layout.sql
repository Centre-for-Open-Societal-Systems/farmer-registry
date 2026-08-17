-- Farmer detail and intake share this Birth Information section. The base
-- Gregorian field remains authoritative; the extension adds the separately
-- captured Ethiopian-calendar value and presents estimated_age as Age.
UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = $schema$
{
  "panels": [
    {
      "widgets": [
        {
          "widget": "date",
          "widget-id": "birth_date",
          "widget-type": "input",
          "widget-label": "birth_date",
          "widget-readonly": false,
          "widget-required": false,
          "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.birth_date",
          "widget-data-format": {"dateFormat": "DD/MM/YYYY", "dateConstraint": "past-only"},
          "widget-data-placeholder": "dd_mm_yyyy"
        },
        {
          "widget": "date",
          "widget-id": "birth_date_ec",
          "widget-type": "input",
          "widget-label": "birth_date_ec",
          "widget-readonly": false,
          "widget-required": false,
          "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.birth_date_ec",
          "widget-data-format": {"dateFormat": "DD/MM/YYYY"},
          "widget-data-placeholder": "dd_mm_yyyy"
        },
        {
          "widget": "number",
          "widget-id": "estimated_age",
          "widget-type": "input",
          "widget-label": "estimated_age",
          "widget-readonly": false,
          "widget-required": false,
          "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.estimated_age",
          "widget-data-validation": {"min": 0, "max": 122}
        }
      ],
      "panel-id": "panel_birth_information_main",
      "panel-title": "birth_information",
      "panel-column-span": 2,
      "panel-orientation": "vertical"
    }
  ],
  "section-id": "farmer_birth_information",
  "section-title": "farmer_birth_information",
  "section-editable": true,
  "section-column-span": 3
}
$schema$::json
WHERE "section_id" = 'farmer_farmer_birth_information_section_01';
