-- Rows that earlier seeds wrote and that no current seed writes. Seed upserts
-- never delete, so a database that lived through those seeds keeps them and,
-- for attachments, shows their sections twice on the forms. Every id here is
-- named explicitly; nothing is removed by NOT IN, so a row upstream adds later
-- is untouched. A fresh database has none of these and this file changes
-- nothing.
--
-- Deletes run in dependency order: an attachment before its tab and its
-- section, a template before its document, the ingestion rows before their
-- data model. 90_checks.sql fails the seed if an OAN-owned section or
-- attachment id with the retired "oan_" prefix is still there.

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

-- The OAN attachments under their earlier ids ('oan_' plus the upstream row's
-- id, or an 'oan_' name), now <tab_id>__<section_id>, farmer_intake__<section_id>
-- and household_intake__<section_id> (20_layout.sql), and those of the retired
-- "names in other languages" section.
DELETE FROM "public"."g2p_intake_form_ui_tab_sections"
WHERE "tab_section_id" IN (
  'oan_tab_section_1', 'oan_tab_section_3', 'oan_tab_section_4', 'oan_tab_section_5',
  'oan_tab_section_6', 'oan_tab_section_9', 'oan_hh_tab_section_1',
  'oan_46392474-53a0-4737-ab8e-c942efc73153', 'oan_bb3542b4-2f6b-443e-b9b5-65ce0b0a6eb8',
  'oan_e0506ad7-657c-4f5d-807e-3ad430dcb639', 'oan_d6873c11-1f86-45f5-9fef-9ad6c8c22303',
  'oan_farmer_name_intake', 'oan_farmer_personal_details_intake', 'oan_farmer_phones_intake',
  'oan_farmer_photo_intake', 'oan_farmer_household_information_intake',
  'oan_farmer_household_members_intake', 'oan_farmer_names_intake'
);

DELETE FROM "public"."g2p_register_ui_tab_sections"
WHERE "tab_section_id" IN (
  'oan_a6ab60bd-07be-4237-aefd-7f6e3c1ced4f', 'oan_9a1573a0-6507-47b6-a717-a007435d2c76',
  'oan_14691011-f41c-4010-be96-af39207b5fc3', 'oan_41a866b7-d301-46e3-8375-17ebb9f0059d',
  'oan_b46853a4-ba5b-4378-ae62-9a274448ac65', 'oan_7c46c33d-9519-4027-b071-3a7e8822ae87',
  'oan_f1a2b3c4-d5e6-4789-a012-3456789abcde', 'oan_a163b218-32d6-49a7-99b6-05d4aeb31f0d',
  'oan_d8753df5-d511-4c63-b045-ff9720a31808', 'oan_6a759aa9-b1cb-47c6-a1ed-db0b3d022f1d',
  'oan_858fead4-9d8b-4f76-9915-7d591b1f4559',
  'oan_farmer_identity_verification_register', 'oan_farmer_name_register',
  'oan_farmer_personal_details_register', 'oan_farmer_phones_tab_section',
  'oan_farmer_land_summary_tab_section', 'oan_farmer_enumerator_tab_section',
  'oan_farmer_names_register'
);

-- The Enumerator tab under its earlier id, now farmer_tab_enumerator.
DELETE FROM "public"."g2p_register_ui_tabs" WHERE "tab_id" = 'oan_farmer_enumerator_tab';

-- The OAN sections under their earlier ids, now named after the farmer's data
-- they hold (10_sections.sql), and the retired "names in other languages"
-- section with its FarmerName register, replaced by the farmer's own-language
-- name in the Name section.
DELETE FROM "public"."g2p_register_sections"
WHERE "section_id" IN (
  'oan_farmer_personal_identification', 'oan_farmer_identity_verification', 'oan_farmer_name',
  'oan_farmer_personal_details', 'oan_farmer_socio_economic_and_health', 'oan_farmer_location',
  'oan_farmer_photo', 'oan_farmer_phones', 'oan_farmer_documents', 'oan_farmer_household_lookup',
  'oan_household_information', 'oan_farmer_membership_details', 'oan_farmer_lands',
  'oan_farmer_land_summary', 'oan_farmer_crops', 'oan_farmer_crops_intake', 'oan_farmer_livestock',
  'oan_farmer_livestock_intake', 'oan_farmer_farm_inputs', 'oan_farmer_farm_inputs_intake',
  'oan_farmer_enumerator', 'oan_farmer_names'
);
DELETE FROM "public"."g2p_register_schemas" WHERE "register_id" = 'd2a7c3e4-5b6f-4a8e-9c1d-2e3f4a5b6c7d';
DELETE FROM "public"."g2p_register_definitions" WHERE "register_id" = 'd2a7c3e4-5b6f-4a8e-9c1d-2e3f4a5b6c7d';

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

-- ODK ingestion rows under their earlier ids, now odk_to_farmer_intake_*
-- (60_odk_ingestion.sql). The connector's data model mnemonic,
-- FARMER_ODK_MODEL, is unchanged; only the row ids move.
DELETE FROM "public"."incoming_templates" WHERE "template_id" = 'IN-TMPL-ODK';
DELETE FROM "public"."g2p_registry_documents" WHERE "document_id" = 'farmer-odk-tmpl-doc';
DELETE FROM "public"."incoming_model_semantic_patterns" WHERE "semantic_pattern_id" = 'farmer_odk_semantic_pattern';
DELETE FROM "public"."incoming_model_key_paths" WHERE "key_path_id" = 'farmer_key_path';
DELETE FROM "public"."data_models" WHERE "data_model_id" = 'FARMER_ODK_MODEL';

-- Outgestion rows under their earlier ids, now farmer_reference_changed_v1_*
-- and farmer_dci_search_response_document (50_outgestion.sql). The data model
-- (FARMER_REFERENCE_CHANGED_V1), the event type and the WebSub topic name are
-- unchanged. Upstream's OUT-TMPL-1 is repointed by 50_outgestion.sql.
DELETE FROM "public"."outgoing_topics" WHERE "topic_id" = '6d495cab-b513-5fd0-9bc2-d31024ee8410';
DELETE FROM "public"."outgoing_templates" WHERE "template_id" = 'b011d78e-b003-596b-a8a1-ba5c73601635';
DELETE FROM "public"."g2p_registry_documents"
WHERE "document_id" IN ('4ece1dd5-2478-5679-8848-292754cf0a0f', 'b6f1c2a0-0a4e-5c1d-9e7a-0a4f1e2d3c01');

-- Labels under their earlier keys, now farmer_photo_*, geo_point_*,
-- documents_*, household_* and farmer_tab_enumerator (30_translations.sql);
-- the oan_idv_* keys of the retired OAN verification popup widget; and the
-- doc_* keys that labelled the document lists before they came from Master
-- Data. Removing a key from the JSON is this table's delete.
UPDATE "public"."registry_languages"
SET "domain_translation" = (COALESCE("domain_translation"::jsonb, '{}'::jsonb) - ARRAY[
  'oan_idv_no_fin', 'oan_idv_verify', 'oan_idv_verify_again', 'oan_idv_waiting', 'oan_idv_not_verified',
  'oan_idv_verified', 'oan_idv_failed', 'oan_idv_filled', 'oan_idv_enter_fin', 'oan_idv_popup_blocked',
  'oan_idv_closed', 'oan_idv_fin_changed',
  'oan_photo_upload', 'oan_photo_replace', 'oan_photo_remove', 'oan_photo_hint', 'oan_photo_none',
  'oan_photo_bad_type', 'oan_photo_too_large', 'oan_photo_unreadable',
  'oan_docs_add', 'oan_docs_none', 'oan_docs_full', 'oan_docs_view',
  'oan_file_attached', 'oan_file_upload', 'oan_file_replace', 'oan_file_remove', 'oan_file_too_large',
  'oan_file_bad_type',
  'oan_map_use_my_location', 'oan_map_clear', 'oan_map_hint', 'oan_map_outside', 'oan_map_no_boundaries',
  'oan_map_locating', 'oan_map_no_location', 'oan_map_latitude', 'oan_map_longitude', 'oan_map_altitude',
  'oan_household_both', 'oan_household_none', 'farmer_enumerator_tab',
  'doc_fayda', 'doc_kebele_woreda_id', 'doc_passport', 'doc_driving_licence',
  'doc_kebele_confirmation_letter', 'doc_other_government_id', 'doc_first_level_certificate', 'doc_second_level_certificate',
  'doc_rental_agreement', 'doc_sharecropping_agreement', 'doc_lease_allocation_document', 'doc_inheritance_transfer_document',
  'doc_land_office_confirmation', 'doc_cooperative_membership', 'doc_farmer_group_confirmation', 'doc_farmer_card',
  'doc_extension_office_confirmation', 'doc_bank_passbook', 'doc_bank_account_confirmation', 'doc_power_of_attorney',
  'doc_guardianship_document', 'doc_representative_id', 'doc_identity_verification', 'doc_eligibility',
  'doc_record_correction', 'doc_other_purpose'])::json
WHERE "domain_translation" IS NOT NULL;
