-- Rows that earlier seeds attached to the farmer forms and that no current seed
-- writes. Seed upserts never delete, so a database that lived through those
-- seeds keeps them and shows their sections twice on the intake form (the new
-- dev registry on 27 October 2026, and staging on 22 September 2026). Every id
-- here is named explicitly; nothing is removed by NOT IN, so a row upstream
-- adds later is untouched. A fresh database has none of these and this file
-- changes nothing.
--
-- Sections themselves (g2p_register_sections) are left alone: unattached rows
-- are harmless, and stored requests may still name them.

-- Attachments to the farmer intake tab from the pre-1.2 layout and from the
-- previous OAN registry, plus the OAN copies that the old section-matching
-- clone made of them.
DELETE FROM "public"."g2p_intake_form_ui_tab_sections"
WHERE "tab_section_id" IN (
  'tab_section_2', 'tab_section_7', 'tab_section_8', 'tab_section_10',
  'tab_section_15', 'tab_section_16', 'tab_section_17', 'tab_section_18', 'tab_section_19',
  'ts_1', 'ts_2', 'ts_3', 'ts_4', 'ts_5', 'ts_6', 'ts_7', 'ts_8', 'ts_9', 'ts_10',
  'farmer-photo-intake-tab-section-01', 'farmer-phone-intake-tab-section-01',
  'farmer-household-information-intake-section-01',
  'oan_tab_section_2', 'oan_tab_section_7', 'oan_tab_section_8', 'oan_tab_section_10',
  'oan_tab_section_15', 'oan_tab_section_16', 'oan_tab_section_17', 'oan_tab_section_18', 'oan_tab_section_19'
);

-- The enumerator, consent-request and consent-receipt tabs of the earlier
-- farmer form, and the retired "Farmer Web Intake" form with its nine tabs.
-- Their sections stay on the farmer record's own tabs where upstream puts them.
DELETE FROM "public"."g2p_intake_form_ui_tab_sections"
WHERE "tab_section_id" IN ('tab_section_12', 'tab_section_13', 'tab_section_14')
   OR "tab_id" IN (
  'a1a4d25a-1cd4-4356-abac-72482724', 'a1a4d25a-1cd4-4356-abac-72482725', 'a1a4d25a-1cd4-4356-abac-72482726',
  'farmer_intake_form_tab',
  'd3f1c7a0-4b62-4e19-9c85-000000000010', 'd3f1c7a0-4b62-4e19-9c85-000000000020',
  'd3f1c7a0-4b62-4e19-9c85-000000000030', 'd3f1c7a0-4b62-4e19-9c85-000000000040',
  'd3f1c7a0-4b62-4e19-9c85-000000000050', 'd3f1c7a0-4b62-4e19-9c85-000000000060',
  'd3f1c7a0-4b62-4e19-9c85-000000000070', 'd3f1c7a0-4b62-4e19-9c85-000000000080',
  'd3f1c7a0-4b62-4e19-9c85-000000000090');

DELETE FROM "public"."g2p_intake_form_ui_tabs"
WHERE "tab_id" IN (
  'a1a4d25a-1cd4-4356-abac-72482724', 'a1a4d25a-1cd4-4356-abac-72482725', 'a1a4d25a-1cd4-4356-abac-72482726',
  'farmer_intake_form_tab',
  'd3f1c7a0-4b62-4e19-9c85-000000000010', 'd3f1c7a0-4b62-4e19-9c85-000000000020',
  'd3f1c7a0-4b62-4e19-9c85-000000000030', 'd3f1c7a0-4b62-4e19-9c85-000000000040',
  'd3f1c7a0-4b62-4e19-9c85-000000000050', 'd3f1c7a0-4b62-4e19-9c85-000000000060',
  'd3f1c7a0-4b62-4e19-9c85-000000000070', 'd3f1c7a0-4b62-4e19-9c85-000000000080',
  'd3f1c7a0-4b62-4e19-9c85-000000000090');

-- The retired form definition goes only when nothing was ever submitted on it.
DELETE FROM "public"."g2p_intake_form_definitions" d
WHERE d."form_id" = 'd3f1c7a0-4b62-4e19-9c85-6a1f2e0b7d41'
  AND NOT EXISTS (SELECT 1 FROM "public"."g2p_intake_form_submissions" s WHERE s."form_id" = d."form_id");

-- The same earlier layouts on the farmer record's tabs.
DELETE FROM "public"."g2p_register_ui_tab_sections"
WHERE "tab_section_id" IN (
  'farmer-photo-tab-section-01', 'farmer-phone-tab-section-01', 'farmer-household-information-tab-section-01',
  'tab_section_12', 'tab_section_13', 'tab_section_14');
