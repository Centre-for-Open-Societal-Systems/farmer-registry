-- OAN sections that upstream has no counterpart for. 20_layout.sql attaches
-- them.
--
--   oan_farmer_phones         the farmer's phone numbers (FarmerPhone)
--   oan_farmer_land_summary   the farmer's land totals, derived, read only
--   oan_farmer_enumerator     who collected the record, where and when, read
--                             only: filled from the submission and the
--                             enumerator's device, never typed

-- Sections of OAN's own, written out. A table section belongs to the child
-- register (is_list); a read-only section has "section-editable": false.
-- Phone columns are not required: a required column makes the whole table
-- mandatory, and a phone is not required of every farmer.
WITH sections (section_id, section_register_id, mnemonic, description, is_list, weightage, ui) AS (
  VALUES
  ('oan_farmer_phones', 'c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f', 'oan_fr_farmer_phones', 'Farmer phone numbers', true, 5,
   '{"section-id": "farmer_phones", "section-title": "phone_numbers", "section-editable": true,
     "panels": [{"panel-id": "oan_panel_phones", "panel-orientation": "horizontal", "panels": [
       {"panel-id": "oan_panel_phones_table", "panel-column-span": 3, "panel-orientation": "vertical", "widgets": [
         {"widget": "table", "widget-id": "phones_table", "widget-type": "table", "widget-label": "phone_numbers",
          "widget-readonly": false, "widget-data-path": "c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f.records",
          "widget-data-add-label": "add_phone_number", "widget-data-operations": {"add": true, "edit": true, "remove": true},
          "widget-data-columns": [
            {"widget": "select", "column-key": "phone_type", "widget-type": "input", "widget-label": "phone_type",
             "widget-readonly": false, "widget-data-path": "phone_type",
             "widget-data-source": {"type": "static", "options": [
               {"label": "PRIMARY", "value": "PRIMARY"}, {"label": "SECONDARY", "value": "SECONDARY"}, {"label": "OTHER", "value": "OTHER"}]}},
            {"widget": "phone", "column-key": "phone_number", "widget-type": "input", "widget-label": "phone_number",
             "widget-readonly": false, "widget-data-path": "phone_number",
             "widget-data-placeholder": "0912345678", "widget-data-validation": {"maxLength": 20}},
            {"widget": "text", "column-key": "country_code", "widget-type": "input", "widget-label": "country_code",
             "widget-readonly": false, "widget-data-path": "country_code", "widget-data-placeholder": "ET",
             "widget-data-validation": {"maxLength": 3}},
            {"widget": "boolean", "column-key": "is_primary", "widget-type": "input", "widget-label": "is_primary",
             "widget-readonly": false, "widget-data-path": "is_primary"}]}]}]}]}'),

  ('oan_farmer_land_summary', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'oan_fr_farmer_land_summary', 'Farmer land totals', false, 0,
   '{"section-id": "farmer_land_summary", "section-title": "land_summary", "section-editable": false,
     "panels": [{"panel-id": "oan_panel_land_summary", "panel-orientation": "horizontal", "panels": [
       {"panel-id": "oan_panel_land_summary_1", "panel-orientation": "vertical", "widgets": [
         {"widget": "number", "widget-id": "total_land_area", "widget-type": "input", "widget-label": "total_land_area",
          "widget-readonly": true, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.total_land_area"},
         {"widget": "text", "widget-id": "land_ownership", "widget-type": "input", "widget-label": "land_ownership",
          "widget-readonly": true, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.land_ownership"}]},
       {"panel-id": "oan_panel_land_summary_2", "panel-orientation": "vertical", "widgets": [
         {"widget": "number", "widget-id": "total_land_owned_area", "widget-type": "input", "widget-label": "total_land_owned_area",
          "widget-readonly": true, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.total_land_owned_area"},
         {"widget": "number", "widget-id": "total_land_rent_area", "widget-type": "input", "widget-label": "total_land_rent_area",
          "widget-readonly": true, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.total_land_rent_area"}]},
       {"panel-id": "oan_panel_land_summary_3", "panel-orientation": "vertical", "widgets": [
         {"widget": "number", "widget-id": "total_land_crop_sharing_area", "widget-type": "input",
          "widget-label": "total_land_crop_sharing_area", "widget-readonly": true,
          "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.total_land_crop_sharing_area"}]}]}]}'),

  ('oan_farmer_enumerator', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'oan_fr_farmer_enumerator', 'Enumerator details', false, 0,
   '{"section-id": "farmer_enumerator", "section-title": "enumerator", "section-editable": false,
     "panels": [{"panel-id": "oan_panel_enumerator", "panel-orientation": "horizontal", "panels": [
       {"panel-id": "oan_panel_enumerator_1", "panel-orientation": "vertical", "widgets": [
         {"widget": "text", "widget-id": "enumerator_name", "widget-type": "input", "widget-label": "enumerator_name",
          "widget-readonly": true, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.enumerator_name"},
         {"widget": "text", "widget-id": "enumerator_user_id", "widget-type": "input", "widget-label": "enumerator_user_id",
          "widget-readonly": true, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.enumerator_user_id"},
         {"widget": "date", "widget-id": "data_collection_date", "widget-type": "input", "widget-label": "data_collection_date",
          "widget-readonly": true, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.data_collection_date"}]},
       {"panel-id": "oan_panel_enumerator_2", "panel-orientation": "vertical", "widgets": [
         {"widget": "number", "widget-id": "enumerator_latitude", "widget-type": "input", "widget-label": "enumerator_latitude",
          "widget-readonly": true, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.enumerator_latitude"},
         {"widget": "number", "widget-id": "enumerator_longitude", "widget-type": "input", "widget-label": "enumerator_longitude",
          "widget-readonly": true, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.enumerator_longitude"}]},
       {"panel-id": "oan_panel_enumerator_3", "panel-orientation": "vertical", "widgets": [
         {"widget": "number", "widget-id": "enumerator_altitude", "widget-type": "input", "widget-label": "enumerator_altitude",
          "widget-readonly": true, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.enumerator_altitude"},
         {"widget": "number", "widget-id": "enumerator_accuracy", "widget-type": "input", "widget-label": "enumerator_accuracy",
          "widget-readonly": true, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.enumerator_accuracy"}]}]}]}')
)
INSERT INTO "public"."g2p_register_sections" (
  "register_id", "section_id", "section_register_id", "is_core_section", "section_mnemonic",
  "section_description", "documents_required", "no_of_verifications_required", "is_list",
  "section_weightage", "section_ui_schema", "cr_auto_approve_for_bene_portal",
  "cr_auto_approve_for_agent_portal", "cr_auto_approve_for_staff_portal", "cr_auto_approve_for_partner")
SELECT 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', section_id, section_register_id, false, mnemonic,
       description, false, 0, is_list, weightage, ui::jsonb, false, false, false, false
FROM sections
ON CONFLICT ("section_id") DO UPDATE SET
  "register_id" = EXCLUDED."register_id", "section_register_id" = EXCLUDED."section_register_id",
  "section_mnemonic" = EXCLUDED."section_mnemonic", "section_description" = EXCLUDED."section_description",
  "is_list" = EXCLUDED."is_list", "section_weightage" = EXCLUDED."section_weightage",
  "section_ui_schema" = EXCLUDED."section_ui_schema";

-- Apply after both derived and OAN-only sections exist. Walking the full JSON
-- also covers dates in table columns (household members and child registers).
-- This is metadata configuration; the date widget and stored field stay native.
CREATE OR REPLACE FUNCTION pg_temp.oan_ethiopian_dates(node jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  result jsonb;
BEGIN
  IF jsonb_typeof(node) = 'array' THEN
    SELECT COALESCE(jsonb_agg(pg_temp.oan_ethiopian_dates(value) ORDER BY ord), '[]'::jsonb)
      INTO result FROM jsonb_array_elements(node) WITH ORDINALITY AS a(value, ord);
  ELSIF jsonb_typeof(node) = 'object' THEN
    SELECT COALESCE(jsonb_object_agg(key, pg_temp.oan_ethiopian_dates(value)), '{}'::jsonb)
      INTO result FROM jsonb_each(node);
    IF node->>'widget' = 'date' AND COALESCE((node->>'widget-readonly')::boolean, false) = false THEN
      result := result || '{"widget-variant": "ethiopian"}'::jsonb;
      -- Native TableCellDate ignores variants. A registered custom cell type
      -- takes TableWidget's supported WidgetRenderer path and row callback.
      IF node ? 'column-key' THEN
        result := result || '{"widget": "oan-ethiopian-date-input"}'::jsonb;
      END IF;
    END IF;
  ELSE
    result := node;
  END IF;
  RETURN result;
END $$;

UPDATE "public"."g2p_register_sections"
SET section_ui_schema = pg_temp.oan_ethiopian_dates(section_ui_schema)
WHERE section_ui_schema IS NOT NULL;
