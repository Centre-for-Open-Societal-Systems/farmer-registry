-- OAN table sections: each one is an upstream section with OAN columns added,
-- plus the household link and the intake photo section. The form sections
-- (three columns of widgets) are laid out in 12_form_sections.sql.
--
-- The image copies this folder to /seed/meta_data/zz-oan/, so it runs after the
-- farmer seed has upserted its own rows. Every OAN row is derived from the
-- upstream row on each run, so upstream changes to a section reach the OAN copy
-- the next time the seed runs. Upstream rows are never updated; 20_layout.sql
-- only detaches them from the tabs.

-- Sections that only gain widgets: the items are appended to the array at path.
WITH additions (upstream_section_id, oan_section_id, path, items) AS (
  VALUES
  -- Lands table (the register and the intake form share this section). The
  -- land certificate cell is OAN's widget (oan-file-cell): upstream's file
  -- widget cannot be used in a table cell, because the table hides labels in
  -- cells and its upload button is one. A row shows "Attached" once it has a
  -- file: the table formats a cell with a "pattern" by filling its X
  -- characters, so a pattern without any is shown as it is. The area in
  -- hectares is derived from the size and unit when the row is saved.
  ('farmer_farm_farm_details_section_01',
   'oan_farmer_lands',
   '{panels,0,panels,0,widgets,0,widget-data-columns}'::text[],
   '[{"widget": "text", "column-key": "land_id", "widget-type": "input", "widget-label": "land_id",
      "widget-readonly": false, "widget-data-path": "land_id", "widget-data-validation": {"maxLength": 50}},
     {"widget": "text", "column-key": "remark", "widget-type": "input", "widget-label": "remark",
      "widget-readonly": false, "widget-data-path": "remark", "widget-data-validation": {"maxLength": 500}},
     {"widget": "text", "column-key": "land_kebele", "widget-type": "input", "widget-label": "land_kebele",
      "widget-readonly": false, "widget-data-path": "land_kebele", "widget-data-validation": {"maxLength": 100}},
     {"widget": "oan-file-cell", "column-key": "certificate_storage_id", "widget-type": "input",
      "widget-label": "land_certificate", "widget-readonly": false, "widget-data-path": "certificate_storage_id",
      "widget-data-options": {"accept": ".pdf,.jpg,.jpeg,.png", "maxSize": 5242880},
      "widget-data-format": {"pattern": "Attached"}},
     {"widget": "number", "column-key": "area_in_hectare", "widget-type": "input", "widget-label": "area_in_hectare",
      "widget-readonly": true, "widget-data-path": "area_in_hectare",
      "widget-data-format": {"numericType": "decimal", "decimalPlaces": 4, "decimalSeparator": ".", "thousandSeparator": ","}}]'::jsonb),

  -- Crops: whether the crop is diseased, and with what.
  ('farmer_crop_crop_details_section_01', 'oan_farmer_crops', '{panels,0,panels,0,widgets,0,widget-data-columns}'::text[], NULL),
  ('farmer_crop_crop_details_intake_section_01', 'oan_farmer_crops_intake', '{panels,0,panels,0,widgets,0,widget-data-columns}'::text[], NULL),

  -- Household link: whether the farmer heads the household; the household's
  -- head name follows the answer.
  ('farmer_household_lookup_section_01',
   'oan_farmer_household_lookup',
   '{panels,0,panels,0,widgets}'::text[],
   '[{"widget": "select", "widget-id": "is_household_head", "widget-type": "input", "widget-label": "is_household_head",
      "widget-readonly": false, "widget-required": false,
      "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.is_household_head",
      "widget-data-source": {"type": "static", "options": [{"label": "YES", "value": true}, {"label": "NO", "value": false}]}}]'::jsonb),

  -- Livestock tables: gender, condition and production, when the count was
  -- taken and in which season, and disease.
  ('farmer_livestock_livestock_details_section_01', 'oan_farmer_livestock', '{panels,0,panels,0,widgets,0,widget-data-columns}'::text[], NULL),
  ('farmer_livestock_livestock_details_intake_section_01', 'oan_farmer_livestock_intake', '{panels,0,panels,0,widgets,0,widget-data-columns}'::text[], NULL),

  -- Farm input tables: each amount after its "used" answer, then the
  -- livestock's water source, irrigation and machinery.
  ('farmer_farm_input_farm_input_details_section_01', 'oan_farmer_farm_inputs', '{panels,0,panels,0,widgets,0,widget-data-columns}'::text[], NULL),
  ('farmer_farm_input_farm_input_details_intake_section_01', 'oan_farmer_farm_inputs_intake', '{panels,0,panels,0,widgets,0,widget-data-columns}'::text[], NULL)
),
shared_columns (oan_section_id, items) AS (
  SELECT oan_section_id, cols FROM (VALUES ('oan_farmer_livestock'), ('oan_farmer_livestock_intake')) s(oan_section_id),
  LATERAL (SELECT '[{"widget": "select", "column-key": "gender", "widget-type": "input", "widget-label": "gender",
      "widget-readonly": false, "widget-data-path": "gender",
      "widget-data-source": {"type": "api", "method": "POST", "params": {"attribute_id": "GENDER"}, "service": "attributes", "endpoint": "values", "labelKey": "value_display", "valueKey": "value_code"}},
     {"widget": "select", "column-key": "body_condition", "widget-type": "input", "widget-label": "body_condition",
      "widget-readonly": false, "widget-data-path": "body_condition",
      "widget-data-source": {"type": "api", "method": "POST", "params": {"attribute_id": "LIVESTOCK_BODY_CONDITION"},
                             "service": "attributes", "endpoint": "values", "labelKey": "value_display", "valueKey": "value_code"}},
     {"widget": "select", "column-key": "production_type", "widget-type": "input", "widget-label": "production_type",
      "widget-readonly": false, "widget-data-path": "production_type",
      "widget-data-source": {"type": "api", "method": "POST", "params": {"attribute_id": "LIVESTOCK_PRODUCTION_TYPE"},
                             "service": "attributes", "endpoint": "values", "labelKey": "value_display", "valueKey": "value_code"}},
     {"widget": "date", "column-key": "collected_date", "widget-type": "input", "widget-label": "collected_date",
      "widget-readonly": false, "widget-data-path": "collected_date"},
     {"widget": "select", "column-key": "season", "widget-type": "input", "widget-label": "season",
      "widget-readonly": false, "widget-data-path": "season",
      "widget-data-source": {"type": "api", "method": "POST", "params": {"attribute_id": "CROP_SEASON"},
                             "service": "attributes", "endpoint": "values", "labelKey": "value_display", "valueKey": "value_code"}},
     {"widget": "select", "column-key": "is_diseased", "widget-type": "input", "widget-label": "is_diseased",
      "widget-readonly": false, "widget-data-path": "is_diseased",
      "widget-data-source": {"type": "static", "options": [{"label": "YES", "value": true}, {"label": "NO", "value": false}]}},
     {"widget": "text", "column-key": "disease_type", "widget-type": "input", "widget-label": "disease_type",
      "widget-readonly": false, "widget-data-path": "disease_type", "widget-data-validation": {"maxLength": 100},
      "widget-data-options": {"actions": [
        {"action": "show", "condition": {"field": "is_diseased", "value": true, "operator": "equals"}}]}}]'::jsonb) c(cols)
  UNION ALL
  SELECT oan_section_id, '[{"widget": "select", "column-key": "is_diseased", "widget-type": "input", "widget-label": "is_diseased",
      "widget-readonly": false, "widget-data-path": "is_diseased",
      "widget-data-source": {"type": "static", "options": [{"label": "YES", "value": true}, {"label": "NO", "value": false}]}},
     {"widget": "select", "column-key": "disease_type", "widget-type": "input", "widget-label": "disease_type",
      "widget-readonly": false, "widget-data-path": "disease_type",
      "widget-data-source": {"type": "api", "method": "POST", "params": {"attribute_id": "INFESTATION_AGENT"},
                             "service": "attributes", "endpoint": "values", "labelKey": "value_display", "valueKey": "value_code"},
      "widget-data-options": {"actions": [
        {"action": "show", "condition": {"field": "is_diseased", "value": true, "operator": "equals"}}]}}]'::jsonb
  FROM (VALUES ('oan_farmer_crops'), ('oan_farmer_crops_intake')) s(oan_section_id)
  UNION ALL
  -- Each amount shows only when the matching "used" answer is yes.
  SELECT oan_section_id, (
    SELECT jsonb_agg(jsonb_build_object(
      'widget', 'number', 'column-key', amount, 'widget-type', 'input', 'widget-label', amount,
      'widget-readonly', false, 'widget-data-path', amount,
      'widget-data-format', jsonb_build_object('allowSigned', false, 'numericType', 'decimal', 'decimalPlaces', 3,
                                               'decimalSeparator', '.', 'thousandSeparator', ','),
      'widget-data-validation', jsonb_build_object('min', 0),
      'widget-data-options', jsonb_build_object('actions', jsonb_build_array(
        jsonb_build_object('action', 'show', 'condition', jsonb_build_object('field', used, 'value', true, 'operator', 'equals'))))
    ) ORDER BY ord)
    FROM (VALUES (1, 'amount_fertilizer_utilized', 'fertilizer_use'),
                 (2, 'amount_pesticide_utilized', 'pesticide_use'),
                 (3, 'amount_insecticide_utilized', 'insecticide_use'),
                 (4, 'amount_improved_seed_utilized', 'improved_seed_use')) a(ord, amount, used))
  || (SELECT jsonb_agg(jsonb_build_object(
      'widget', 'select', 'column-key', field, 'widget-type', 'input', 'widget-label', field,
      'widget-readonly', false, 'widget-data-path', field,
      'widget-data-source', jsonb_build_object('type', 'api', 'method', 'POST', 'params', jsonb_build_object('attribute_id', list),
                                               'service', 'attributes', 'endpoint', 'values',
                                               'labelKey', 'value_display', 'valueKey', 'value_code')) ORDER BY ord)
      FROM (VALUES (1, 'livestock_water_source', 'WATER_SOURCE'),
                   (2, 'irrigation_type', 'IRRIGATION_METHOD'),
                   (3, 'machinery_type', 'FARM_MACHINERY')) l(ord, field, list))
  FROM (VALUES ('oan_farmer_farm_inputs'), ('oan_farmer_farm_inputs_intake')) s(oan_section_id)
)
INSERT INTO "public"."g2p_register_sections" (
  "register_id", "section_id", "section_register_id", "is_core_section", "section_mnemonic",
  "section_description", "documents_required", "no_of_verifications_required", "is_list",
  "section_weightage", "section_ui_schema", "cr_auto_approve_for_bene_portal",
  "cr_auto_approve_for_agent_portal", "cr_auto_approve_for_staff_portal", "cr_auto_approve_for_partner")
SELECT u.register_id, a.oan_section_id, u.section_register_id, u.is_core_section, 'oan_' || u.section_mnemonic,
       u.section_description, u.documents_required, u.no_of_verifications_required, u.is_list,
       u.section_weightage,
       jsonb_set(u.section_ui_schema, a.path,
                 (u.section_ui_schema #> a.path) || COALESCE(a.items, s.items)),
       u.cr_auto_approve_for_bene_portal, u.cr_auto_approve_for_agent_portal,
       u.cr_auto_approve_for_staff_portal, u.cr_auto_approve_for_partner
FROM additions a
JOIN "public"."g2p_register_sections" u ON u.section_id = a.upstream_section_id
LEFT JOIN shared_columns s ON s.oan_section_id = a.oan_section_id
WHERE jsonb_typeof(u.section_ui_schema #> a.path) = 'array'
ON CONFLICT ("section_id") DO UPDATE SET
  "register_id" = EXCLUDED."register_id", "section_register_id" = EXCLUDED."section_register_id",
  "is_core_section" = EXCLUDED."is_core_section", "section_mnemonic" = EXCLUDED."section_mnemonic",
  "section_description" = EXCLUDED."section_description", "documents_required" = EXCLUDED."documents_required",
  "no_of_verifications_required" = EXCLUDED."no_of_verifications_required", "is_list" = EXCLUDED."is_list",
  "section_weightage" = EXCLUDED."section_weightage", "section_ui_schema" = EXCLUDED."section_ui_schema",
  "cr_auto_approve_for_bene_portal" = EXCLUDED."cr_auto_approve_for_bene_portal",
  "cr_auto_approve_for_agent_portal" = EXCLUDED."cr_auto_approve_for_agent_portal",
  "cr_auto_approve_for_staff_portal" = EXCLUDED."cr_auto_approve_for_staff_portal",
  "cr_auto_approve_for_partner" = EXCLUDED."cr_auto_approve_for_partner";

-- Farmer photo for the intake form. The register's detail view already has the
-- photo in upstream's header section (fr_farmer_header); the intake form has no
-- header, so without this a photo could only be added after approval.
--
-- The widget is OAN's own (ui/staff-ui/overrides/src/oan/widgets/): one picker
-- (a phone offers its camera or its gallery), preview, replace, remove. The widget
-- package uploads a section's photo, and sets record_image_document_id, the
-- field the detail view's header shows, only for widgets of type
-- "header-section". So the section declares that type, and "widget-variant"
-- selects the OAN widget; every other header-section stays upstream's. It is
-- attached to the intake form only (20_layout.sql), so the detail view does not
-- get a second picker for the same field.
--
-- The section also records where the enumerator is when the form is filled
-- (widget oan-enumerator-position): the device's position, once, if the
-- browser is allowed to give it. It shows nothing on the form; the register's
-- Enumerator tab shows the values.
INSERT INTO "public"."g2p_register_sections" (
  "register_id", "section_id", "section_register_id", "is_core_section", "section_mnemonic",
  "section_description", "documents_required", "no_of_verifications_required", "is_list",
  "section_weightage", "section_ui_schema", "cr_auto_approve_for_bene_portal",
  "cr_auto_approve_for_agent_portal", "cr_auto_approve_for_staff_portal", "cr_auto_approve_for_partner")
VALUES (
  'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'oan_farmer_photo', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', false,
  'oan_fr_farmer_photo', 'Farmer photo', false, 0, false, 0,
  '{"section-id": "farmer_photo", "section-title": "farmer_photo", "section-editable": true, "section-column-span": 3,
    "panels": [{"panel-id": "oan_panel_farmer_photo", "panel-orientation": "vertical", "widgets": [
      {"widget": "header-section", "widget-variant": "oan-farmer-photo", "widget-id": "farmer-photo",
       "widget-type": "group", "widget-label": "farmer_photo", "widget-readonly": false, "widget-required": false,
       "widget-data-path": {"image": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.record_image_document_id",
                            "imageUrl": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.record_image_url"},
       "widget-data-format": {"imageSize": 160, "maxDimension": 1024, "jpegQuality": 0.85},
       "widget-data-validation": {"maxSizeKb": 2048}},
      {"widget": "oan-enumerator-position", "widget-id": "enumerator-position", "widget-type": "input",
       "widget-readonly": false, "widget-required": false,
       "widget-data-path": {"latitude": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.enumerator_latitude",
                            "longitude": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.enumerator_longitude",
                            "altitude": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.enumerator_altitude",
                            "accuracy": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.enumerator_accuracy"}}]}]}'::jsonb,
  false, false, false, false)
ON CONFLICT ("section_id") DO UPDATE SET
  "register_id" = EXCLUDED."register_id", "section_register_id" = EXCLUDED."section_register_id",
  "section_mnemonic" = EXCLUDED."section_mnemonic", "section_description" = EXCLUDED."section_description",
  "section_ui_schema" = EXCLUDED."section_ui_schema";

-- The household of a new farmer is either one already registered, picked in
-- the household lookup, or a new one, entered in the household sections of
-- the farmer intake form (20_layout.sql). Upstream requires the lookup, which
-- would make a new household impossible to enter, so OAN's copy of the lookup
-- is optional and says which to do.
UPDATE "public"."g2p_register_sections" s
SET "section_ui_schema" = jsonb_set(s."section_ui_schema", '{panels,0,panels,0,widgets}', (
  SELECT jsonb_agg(CASE WHEN w ->> 'widget-id' = 'household_lookup'
                        THEN w || '{"widget-required": false, "widget-data-helptext": "household_lookup_helptext"}'::jsonb
                        ELSE w END ORDER BY i)
  FROM jsonb_array_elements(s."section_ui_schema" #> '{panels,0,panels,0,widgets}') WITH ORDINALITY x(w, i)))
WHERE s."section_id" = 'oan_farmer_household_lookup'
  AND jsonb_typeof(s."section_ui_schema" #> '{panels,0,panels,0,widgets}') = 'array';
