-- Farmer detail and intake share this Birth Information section. The base
-- Gregorian field remains authoritative; the extension adds the separately
-- captured Ethiopian-calendar value and presents estimated_age as Age.
--
-- Gender is captured here, with the birth details it is read alongside (Gen1
-- parity), rather than as a stray row under the name grid in Personal
-- Information (zz_farmer_personal_socio_layout.sql).
UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = $schema$
{
  "panels": [
    {
      "widgets": [
        {
          "widget": "select",
          "widget-id": "gender",
          "widget-type": "input",
          "widget-label": "gender",
          "widget-readonly": false,
          "widget-required": false,
          "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.gender",
          "widget-data-source": {"type": "static", "options": [{"label": "MALE", "value": "MALE"}, {"label": "FEMALE", "value": "FEMALE"}, {"label": "OTHERS", "value": "OTHERS"}, {"label": "UNKNOWN", "value": "UNKNOWN"}]}
        },
        {
          "widget": "text",
          "widget-id": "birth_date",
          "widget-type": "input",
          "widget-label": "birth_date",
          "widget-readonly": false,
          "widget-required": false,
          "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.birth_date",
          "widget-data-placeholder": "yyyy_mm_dd",
          "widget-data-validation": {"pattern": "^\\d{4}-\\d{2}-\\d{2}$", "patternMessage": "Enter the date as YYYY-MM-DD, e.g. 1990-05-15"}
        },
        {
          "widget": "text",
          "widget-id": "birth_date_ec",
          "widget-type": "input",
          "widget-label": "birth_date_ec",
          "widget-readonly": false,
          "widget-required": false,
          "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.birth_date_ec",
          "widget-data-placeholder": "yyyy_mm_dd_ec",
          "widget-data-validation": {"pattern": "^\\d{4}-\\d{2}-\\d{2}$", "patternMessage": "Enter the Ethiopian date as YYYY-MM-DD, e.g. 2015-01-05"}
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
