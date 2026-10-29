-- Readable text, second pass: what the readability audit of the Farmer registry
-- found in the staff screens. Display text only; no id, code, path or
-- validation changes. Every statement is a merge of named translation keys or
-- an UPDATE of named sections, so it is idempotent. It sorts after
-- 85_readable_text.sql and wins over it; 88_readable_text_checks.sql fails the
-- seed if a label reads like a code.
--
-- The staff UI shows a value through its translation when a key matches it, so
-- a code that has a key (FEMALE, PRIMARY, DRAFT) reads as text in the lists
-- that translate values. The register list's desktop table prints the raw value
-- whatever the keys are; that is the table widget, not this metadata.

-- Platform screen text: the registry platform's English is Title Case on every
-- officer screen. Sentence case here, same meaning, through core translations
-- (the language row's core text, merged by key, so keys not named stay as they are).
UPDATE "public"."registry_languages"
SET "core_translation" = (COALESCE("core_translation"::jsonb, '{}'::jsonb) ||
'{
 "access_denied": "Access denied",
 "application_reference": "Application reference",
 "approval_status": "Approval status",
 "approved_at": "Approved at",
 "approved_by": "Approved by",
 "assignee_name": "Assignee name",
 "attached_documents": "Attached documents",
 "change_request": "Change request",
 "change_requests": "Change requests",
 "tasks_cr": "Change requests",
 "clear_all": "Clear all",
 "completed_at": "Completed at",
 "cr_possible_duplicates": "CR possible duplicates",
 "create_new_submission": "Create new submission",
 "created_at": "Created at",
 "created_by": "Created by",
 "credential_type": "Credential type",
 "decision_action": "Decision action",
 "dedup_result_id": "Dedup result ID",
 "document_icon_alt": "Document icon",
 "draft_submissions": "Draft submissions",
 "edit_image": "Edit image",
 "enriched_message": "Enriched message",
 "export_again": "Export again",
 "export_history": "Export history",
 "export_records": "Export records",
 "finalised_at": "Finalised at",
 "form_details": "Form details",
 "form_status": "Form status",
 "form_submissions": "Form submissions",
 "go_back": "Go back",
 "import_file": "Import file",
 "import_successful": "Import successful",
 "incoming_messages": "Incoming messages",
 "tasks_intake": "Intake form submissions",
 "intake_forms": "Intake forms",
 "intake_possible_duplicates": "Intake possible duplicates",
 "know_more": "Know more",
 "last_approved_by": "Last approved by",
 "last_updated_by": "Last updated by",
 "match_score": "Match score",
 "my_profile": "My profile",
 "approval_tasks": "My tasks",
 "new_and_old_values": "New & old values",
 "new_intake": "New intake",
 "no_change_request": "No change request",
 "no_tab_section": "No tab section",
 "no_version_history": "No version history",
 "outgoing_messages": "Outgoing messages",
 "pending_requests": "Pending requests",
 "pending_submissions": "Pending submissions",
 "raw_message": "Raw message",
 "record_access_denied": "Record access denied",
 "register_possible_duplicates": "Register possible duplicates",
 "registryGen2": "Registry gen 2",
 "retry_export": "Retry export",
 "search_change_requests": "Search change requests",
 "search_form_submissions": "Search in form submissions",
 "search_messages": "Search messages",
 "search_approval_tasks": "Search my tasks",
 "search_registers": "Search records in register",
 "select_date": "Select date",
 "select_operator": "Select operator",
 "select_section": "Select section",
 "select_version": "Select version",
 "export_start": "Start export",
 "total_versions": "Total versions",
 "transformed_message": "Transformed message",
 "updated_at": "Updated at",
 "upload_file": "Upload file",
 "verification_result": "Verification result",
 "verify_credential": "Verify credential",
 "version_history": "Version history",
 "view_less": "View less",
 "view_more": "View more",
 "view_queue": "View queue",
 "register_form_submissions": "{subject} - form submissions",
 "register_intake_form": "{subject} - intake form",
 "common.remove": "Remove",
 "common.select": "Select",
 "kind": "Task type"
}'::jsonb)::json
WHERE "language_code" = 'en';

-- Domain text (English)
UPDATE "public"."registry_languages"
SET "domain_translation" = (COALESCE("domain_translation"::jsonb, '{}'::jsonb) ||
'{
 "region_name": "Region name",
 "zone_name": "Zone name",
 "woreda_name": "Woreda name",
 "kebele_name": "Kebele name",
 "farmer_phones": "Farmer phones",
 "fr_farmer_phone_numbers": "Farmer phone numbers",
 "fr_farmer_reg_ids": "Farmer identification",
 "farmer_documents": "Documents",
 "farmer_socio_economic_health": "Socio-economic and health",
 "DRAFT": "Draft",
 "FINAL": "Final",
 "REJECTED": "Rejected",
 "STAFF_PORTAL": "Staff portal",
 "NON_FORMAL": "Non-formal education",
 "NEVER_ATTEND": "Never attended school",
 "PRIMARY": "Primary",
 "SECONDARY": "Secondary",
 "TERTIARY": "Tertiary",
 "HIGHER_EDUCATION": "Higher education",
 "MR": "Mr",
 "MRS": "Mrs",
 "MS": "Ms",
 "DR": "Dr",
 "MISS": "Miss",
 "Farmer Ingestion Intake": "Farmer registration",
 "Household Ingestion Intake": "Household registration",
 "farmer_ingestion_intake": "Farmer registration",
 "household_ingestion_intake": "Household registration",
 "has_national_id": "Has a Fayda ID",
 "fayda_fin_format": "Enter the Fayda ID as a 12-digit FIN or a 16-digit FAN, using digits only. Verification is optional; upload ID evidence for approval.",
 "identity_verification": "Fayda ID verification",
 "fertilizer_use": "Uses fertilizer",
 "amount_fertilizer_utilized": "Amount of fertilizer used",
 "pesticide_use": "Uses pesticide",
 "amount_pesticide_utilized": "Amount of pesticide used",
 "insecticide_use": "Uses insecticide",
 "amount_insecticide_utilized": "Amount of insecticide used",
 "improved_seed_use": "Uses improved seed",
 "amount_improved_seed_utilized": "Amount of improved seed used"
}'::jsonb)::json
WHERE "language_code" = 'en';

-- Crop, livestock and farm-input rows pick the land they belong to; the
-- lookup said "Parent". The stored link and the lookup service are unchanged.
UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(replace(replace(replace(section_ui_schema::text,
  '"widget-label": "Parent"', '"widget-label": "Land"'),
  '"search_placeholder": "Search parent..."', '"search_placeholder": "Search land..."'),
  '"select_record_label": "Select Parent"', '"select_record_label": "Select land"'),
  '"select_record_label": "Select parent"', '"select_record_label": "Select land"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd'
  AND "section_id" IN ('farmer_crops', 'farmer_crops_intake', 'farmer_livestock', 'farmer_livestock_intake',
                       'farmer_farm_inputs', 'farmer_farm_inputs_intake',
                       'farmer_crop_crop_details_section_01', 'farmer_crop_crop_details_intake_section_01',
                       'farmer_livestock_livestock_details_section_01', 'farmer_livestock_livestock_details_intake_section_01',
                       'farmer_farm_input_farm_input_details_section_01', 'farmer_farm_input_farm_input_details_intake_section_01');

-- The registration forms: one name wherever staff see them.
UPDATE "public"."g2p_intake_form_definitions" SET "form_description" = 'Farmer registration'
WHERE "form_id" = 'a1a4d25a-1cd4-4356-abac-8782382649';
UPDATE "public"."g2p_intake_form_definitions" SET "form_description" = 'Household registration'
WHERE "form_id" = '9055ab43-c85d-4833-bd00-ca657bb72650';
