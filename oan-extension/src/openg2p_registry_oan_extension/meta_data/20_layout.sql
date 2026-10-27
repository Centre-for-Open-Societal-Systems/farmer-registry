-- Put the OAN sections where the upstream ones were, on the register tabs and
-- the intake form, then detach the upstream sections from those places. The
-- Farmer Personal Information replacement is split into identity, name and
-- personal-details sections; all three stay adjacent before the photo/location
-- sections.
--
-- Each OAN attachment copies the tab and order of the upstream one it replaces.
-- Both the copy and the removal name the upstream row by its tab_section_id,
-- never by section: a long-lived database carries rows from earlier seeds that
-- point at the same sections, and matching by section once cloned one of them
-- (oan_tab_section_19) next to the real one, so Membership showed twice. A row
-- upstream adds later is left alone; 22_retired_rows.sql drops the known
-- leftovers. The farmer seed re-inserts the upstream rows on every run, and
-- this file removes them again right after.

WITH replaced (upstream_tab_section_id, upstream_section_id, oan_section_id) AS (
  VALUES ('a6ab60bd-07be-4237-aefd-7f6e3c1ced4f', 'farmer_farmer_personal_identification_section_01', 'oan_farmer_personal_identification'),
         ('9a1573a0-6507-47b6-a717-a007435d2c76', 'farmer_farmer_socio_economic_and_health_section_04', 'oan_farmer_socio_economic_and_health'),
         ('14691011-f41c-4010-be96-af39207b5fc3', 'farmer_membership_membership_details_01', 'oan_farmer_membership_details'),
         ('41a866b7-d301-46e3-8375-17ebb9f0059d', 'farmer_farm_farm_details_section_01', 'oan_farmer_lands'),
         ('b46853a4-ba5b-4378-ae62-9a274448ac65', 'farmer_livestock_livestock_details_section_01', 'oan_farmer_livestock'),
         ('7c46c33d-9519-4027-b071-3a7e8822ae87', 'farmer_farm_input_farm_input_details_section_01', 'oan_farmer_farm_inputs'),
         ('f1a2b3c4-d5e6-4789-a012-3456789abcde', 'farmer_household_lookup_section_01', 'oan_farmer_household_lookup'),
         ('a163b218-32d6-49a7-99b6-05d4aeb31f0d', 'farmer_crop_crop_details_section_01', 'oan_farmer_crops'),
         ('d8753df5-d511-4c63-b045-ff9720a31808', 'farmer_farmer_location_section_03', 'oan_farmer_location'),
         ('6a759aa9-b1cb-47c6-a1ed-db0b3d022f1d', 'household_household_household_information_section_01', 'oan_household_information'),
         ('858fead4-9d8b-4f76-9915-7d591b1f4559', 'bc882922-9008-4902-8f4f-98db0fa8f9ad', 'oan_farmer_documents')
)
INSERT INTO "public"."g2p_register_ui_tab_sections" ("tab_section_id", "register_id", "tab_id", "section_id", "section_order")
SELECT 'oan_' || t.tab_section_id, t.register_id, t.tab_id, r.oan_section_id, t.section_order
FROM "public"."g2p_register_ui_tab_sections" t
JOIN replaced r ON r.upstream_tab_section_id = t.tab_section_id AND r.upstream_section_id = t.section_id
JOIN "public"."g2p_register_sections" s ON s.section_id = r.oan_section_id
ON CONFLICT ("tab_section_id") DO UPDATE SET
  "register_id" = EXCLUDED."register_id", "tab_id" = EXCLUDED."tab_id",
  "section_id" = EXCLUDED."section_id", "section_order" = EXCLUDED."section_order";

-- Split Personal Information into three adjacent sections. The UI section-id
-- is rewritten in 12_form_sections.sql because MultiSectionAccordionForms
-- matches saves by UI section-id; copied upstream ids would collide.
INSERT INTO "public"."g2p_register_ui_tab_sections" ("tab_section_id", "register_id", "tab_id", "section_id", "section_order")
SELECT v.tab_section_id, t.register_id, t.tab_id, v.section_id, t.section_order + v.order_offset
FROM "public"."g2p_register_ui_tab_sections" t
JOIN (VALUES
  ('oan_farmer_name_register', 'oan_farmer_name', 1),
  ('oan_farmer_personal_details_register', 'oan_farmer_personal_details', 2)
) v(tab_section_id, section_id, order_offset) ON true
JOIN "public"."g2p_register_sections" s ON s.section_id = v.section_id
WHERE t.tab_id = 'farmer_farmer_tab'
  AND t.section_id = 'oan_farmer_personal_identification'
ON CONFLICT ("tab_section_id") DO UPDATE SET
  "register_id" = EXCLUDED."register_id", "tab_id" = EXCLUDED."tab_id",
  "section_id" = EXCLUDED."section_id", "section_order" = EXCLUDED."section_order";

WITH replaced (upstream_tab_section_id, upstream_section_id, oan_section_id) AS (
  VALUES ('tab_section_3', 'farmer_farmer_personal_identification_section_01', 'oan_farmer_personal_identification'),
         ('tab_section_4', 'farmer_farmer_socio_economic_and_health_section_04', 'oan_farmer_socio_economic_and_health'),
         ('tab_section_9', 'farmer_membership_membership_details_01', 'oan_farmer_membership_details'),
         ('tab_section_6', 'farmer_farm_farm_details_section_01', 'oan_farmer_lands'),
         ('46392474-53a0-4737-ab8e-c942efc73153', 'farmer_livestock_livestock_details_intake_section_01', 'oan_farmer_livestock_intake'),
         ('bb3542b4-2f6b-443e-b9b5-65ce0b0a6eb8', 'farmer_farm_input_farm_input_details_intake_section_01', 'oan_farmer_farm_inputs_intake'),
         ('e0506ad7-657c-4f5d-807e-3ad430dcb639', 'farmer_crop_crop_details_intake_section_01', 'oan_farmer_crops_intake'),
         ('tab_section_5', 'farmer_farmer_location_section_03', 'oan_farmer_location'),
         ('hh_tab_section_1', 'household_household_household_information_section_01', 'oan_household_information'),
         ('d6873c11-1f86-45f5-9fef-9ad6c8c22303', 'bc882922-9008-4902-8f4f-98db0fa8f9ad', 'oan_farmer_documents')
)
INSERT INTO "public"."g2p_intake_form_ui_tab_sections" ("tab_section_id", "tab_id", "section_id", "section_order")
SELECT 'oan_' || t.tab_section_id, t.tab_id, r.oan_section_id, t.section_order
FROM "public"."g2p_intake_form_ui_tab_sections" t
JOIN replaced r ON r.upstream_tab_section_id = t.tab_section_id AND r.upstream_section_id = t.section_id
JOIN "public"."g2p_register_sections" s ON s.section_id = r.oan_section_id
ON CONFLICT ("tab_section_id") DO UPDATE SET
  "tab_id" = EXCLUDED."tab_id", "section_id" = EXCLUDED."section_id", "section_order" = EXCLUDED."section_order";

INSERT INTO "public"."g2p_intake_form_ui_tab_sections" ("tab_section_id", "tab_id", "section_id", "section_order")
SELECT v.tab_section_id, t.tab_id, v.section_id, t.section_order + v.order_offset
FROM "public"."g2p_intake_form_ui_tab_sections" t
JOIN (VALUES
  ('oan_farmer_name_intake', 'oan_farmer_name', 1),
  ('oan_farmer_personal_details_intake', 'oan_farmer_personal_details', 2)
) v(tab_section_id, section_id, order_offset) ON true
JOIN "public"."g2p_register_sections" s ON s.section_id = v.section_id
WHERE t.tab_id = 'a1a4d25a-1cd4-4356-abac-72482721'
  AND t.section_id = 'oan_farmer_personal_identification'
ON CONFLICT ("tab_section_id") DO UPDATE SET
  "tab_id" = EXCLUDED."tab_id", "section_id" = EXCLUDED."section_id", "section_order" = EXCLUDED."section_order";

-- OAN's tab on the farmer's record: Enumerator. Location stays on the farmer
-- tab, as OpenG2P recommends.
INSERT INTO "public"."g2p_register_ui_tabs" ("tab_id", "register_id", "tab_label", "tab_order", "is_active")
VALUES ('oan_farmer_enumerator_tab', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_enumerator_tab', 40, true)
ON CONFLICT ("tab_id") DO UPDATE SET
  "register_id" = EXCLUDED."register_id", "tab_label" = EXCLUDED."tab_label",
  "tab_order" = EXCLUDED."tab_order", "is_active" = EXCLUDED."is_active";

-- OAN sections on the farmer's record.
INSERT INTO "public"."g2p_register_ui_tab_sections" ("tab_section_id", "register_id", "tab_id", "section_id", "section_order")
SELECT v.tab_section_id, 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', v.tab_id, v.section_id, v.section_order
FROM (VALUES
  ('oan_farmer_phones_tab_section', 'farmer_farmer_tab', 'oan_farmer_phones', 13),
  ('oan_farmer_land_summary_tab_section', 'farmer_land_tab', 'oan_farmer_land_summary', 5),
  ('oan_farmer_enumerator_tab_section', 'oan_farmer_enumerator_tab', 'oan_farmer_enumerator', 10)
) v(tab_section_id, tab_id, section_id, section_order)
JOIN "public"."g2p_register_sections" s ON s.section_id = v.section_id
JOIN "public"."g2p_register_ui_tabs" t ON t.tab_id = v.tab_id
ON CONFLICT ("tab_section_id") DO UPDATE SET
  "register_id" = EXCLUDED."register_id", "tab_id" = EXCLUDED."tab_id",
  "section_id" = EXCLUDED."section_id", "section_order" = EXCLUDED."section_order";

-- And on the intake form: phones after the photo. The enumerator and the land
-- totals are not asked; they are derived. The household link on the intake
-- form stays upstream's until OpenG2P's design for it is agreed, so the
-- household-head question is on the register only.
INSERT INTO "public"."g2p_intake_form_ui_tab_sections" ("tab_section_id", "tab_id", "section_id", "section_order")
SELECT v.tab_section_id, 'a1a4d25a-1cd4-4356-abac-72482721', v.section_id, v.section_order
FROM (VALUES ('oan_farmer_phones_intake', 'oan_farmer_phones', 27)) v(tab_section_id, section_id, section_order)
JOIN "public"."g2p_register_sections" s ON s.section_id = v.section_id
ON CONFLICT ("tab_section_id") DO UPDATE SET
  "tab_id" = EXCLUDED."tab_id", "section_id" = EXCLUDED."section_id", "section_order" = EXCLUDED."section_order";

-- Detach upstream, only where the OAN replacement is attached.
DELETE FROM "public"."g2p_register_ui_tab_sections"
WHERE "tab_section_id" IN (
  'a6ab60bd-07be-4237-aefd-7f6e3c1ced4f',  -- farmer tab: personal identification
  '9a1573a0-6507-47b6-a717-a007435d2c76',  -- farmer tab: socio-economic and health
  '14691011-f41c-4010-be96-af39207b5fc3',  -- membership tab
  '41a866b7-d301-46e3-8375-17ebb9f0059d',  -- lands tab
  'b46853a4-ba5b-4378-ae62-9a274448ac65',  -- livestock tab
  '7c46c33d-9519-4027-b071-3a7e8822ae87',  -- farm inputs tab
  'f1a2b3c4-d5e6-4789-a012-3456789abcde',  -- household link tab: household lookup
  'a163b218-32d6-49a7-99b6-05d4aeb31f0d',  -- crops tab
  'd8753df5-d511-4c63-b045-ff9720a31808',  -- farmer tab: location
  '6a759aa9-b1cb-47c6-a1ed-db0b3d022f1d',  -- household tab: household information
  '858fead4-9d8b-4f76-9915-7d591b1f4559'   -- farmer tab: documents
)
AND EXISTS (SELECT 1 FROM "public"."g2p_register_ui_tab_sections" o
            WHERE o."tab_section_id" = 'oan_' || "g2p_register_ui_tab_sections"."tab_section_id");

DELETE FROM "public"."g2p_intake_form_ui_tab_sections"
WHERE "tab_section_id" IN (
  'tab_section_3',                         -- personal identification
  'tab_section_4',                         -- socio-economic and health
  'tab_section_6',                         -- lands
  'bb3542b4-2f6b-443e-b9b5-65ce0b0a6eb8',  -- farm inputs
  '46392474-53a0-4737-ab8e-c942efc73153',  -- livestock
  'tab_section_9',                         -- membership
  'tab_section_5',                         -- location
  'e0506ad7-657c-4f5d-807e-3ad430dcb639',  -- crops
  'hh_tab_section_1',                      -- household form: household information
  'd6873c11-1f86-45f5-9fef-9ad6c8c22303'   -- documents
)
AND EXISTS (SELECT 1 FROM "public"."g2p_intake_form_ui_tab_sections" o
            WHERE o."tab_section_id" = 'oan_' || "g2p_intake_form_ui_tab_sections"."tab_section_id");

-- The photo section, on the intake form only, right after personal
-- identification (see 10_sections.sql for why not on the register tabs).
INSERT INTO "public"."g2p_intake_form_ui_tab_sections" ("tab_section_id", "tab_id", "section_id", "section_order")
SELECT 'oan_farmer_photo_intake', t.tab_id, 'oan_farmer_photo', t.section_order + 5
FROM "public"."g2p_intake_form_ui_tab_sections" t
WHERE t.tab_section_id = 'oan_tab_section_3'
ON CONFLICT ("tab_section_id") DO UPDATE SET
  "tab_id" = EXCLUDED."tab_id", "section_id" = EXCLUDED."section_id", "section_order" = EXCLUDED."section_order";

-- The household on the farmer's intake form: its information and its
-- members, after socio-economic and health, as the previous registry asked
-- them. Upstream's intake links a form's rows to their parent register
-- (G2PIntakeFormLinkService): a farmer whose form carries one household row is
-- linked to that household, and its members to it, so the household is created
-- with the farmer on approval. Linking an existing household stays the
-- household lookup at the top of the form; the household intake form keeps
-- the same sections for a household registered on its own.
INSERT INTO "public"."g2p_intake_form_ui_tab_sections" ("tab_section_id", "tab_id", "section_id", "section_order")
SELECT v.tab_section_id, 'a1a4d25a-1cd4-4356-abac-72482721', v.section_id, v.section_order
FROM (VALUES ('oan_farmer_household_information_intake', 'oan_household_information', 33),
             ('oan_farmer_household_members_intake', 'household_household_household_member_section_02', 35)
) v(tab_section_id, section_id, section_order)
JOIN "public"."g2p_register_sections" s ON s.section_id = v.section_id
ON CONFLICT ("tab_section_id") DO UPDATE SET
  "tab_id" = EXCLUDED."tab_id", "section_id" = EXCLUDED."section_id", "section_order" = EXCLUDED."section_order";

-- Retired: the separate "names in other languages" section and its FarmerName
-- register, replaced by the farmer's own-language name in the Name section.
-- Seed upserts never delete, so a registry seeded with them drops them here,
-- by id.
DELETE FROM "public"."g2p_intake_form_ui_tab_sections" WHERE "tab_section_id" = 'oan_farmer_names_intake';
DELETE FROM "public"."g2p_register_ui_tab_sections" WHERE "tab_section_id" = 'oan_farmer_names_register';
DELETE FROM "public"."g2p_register_sections" WHERE "section_id" = 'oan_farmer_names';
DELETE FROM "public"."g2p_register_schemas" WHERE "register_id" = 'd2a7c3e4-5b6f-4a8e-9c1d-2e3f4a5b6c7d';
DELETE FROM "public"."g2p_register_definitions" WHERE "register_id" = 'd2a7c3e4-5b6f-4a8e-9c1d-2e3f4a5b6c7d';
