-- The header of the farmer's record (photo, name, Farmer ID, status and who
-- created or approved it) is upstream's header section with captions of its
-- own. Upstream's captions are Title Case and call the Farmer ID "Functional
-- Record ID"; the header widget lets a section rename each one through
-- "widget-labels", so the OAN copy maps them to translation keys that read in
-- sentence case (87_zz_farmer_tab_text.sql).
--
-- Like the other OAN sections the copy is derived from the upstream row on
-- every run, so upstream changes to the header (paths, colours, image size)
-- reach it. Upstream's row is never updated; 20_layout.sql attaches this one
-- in its place on the Farmer tab and detaches upstream's. The section's id,
-- mnemonic and UI section-id are one string (the UI section-id is the same
-- as upstream's, so a saved photo change reads back to the same section).
-- The upstream row stays in the table, so change requests recorded against it
-- still resolve.

INSERT INTO "public"."g2p_register_sections" (
  "register_id", "section_id", "section_register_id", "is_core_section", "section_mnemonic",
  "section_description", "documents_required", "no_of_verifications_required", "is_list",
  "section_weightage", "section_ui_schema", "cr_auto_approve_for_bene_portal",
  "cr_auto_approve_for_agent_portal", "cr_auto_approve_for_staff_portal", "cr_auto_approve_for_partner")
SELECT u.register_id, 'farmer_header', u.section_register_id, u.is_core_section,
       'farmer_header',
       u.section_description, u.documents_required, u.no_of_verifications_required, u.is_list, u.section_weightage,
       jsonb_set(
         jsonb_set(u.section_ui_schema, '{section-id}', '"farmer_header"'),
         '{panels,0,panels,0,widgets,0,widget-labels}',
         '{"functionalId": "farmer_header_farmer_id", "status": "farmer_header_status",
           "statusReason": "farmer_header_status_reason", "createdBy": "farmer_header_created_by",
           "createdAt": "farmer_header_created_on", "lastApprovedBy": "farmer_header_last_approved_by",
           "lastApprovedAt": "farmer_header_last_approved_on"}'::jsonb),
       u.cr_auto_approve_for_bene_portal, u.cr_auto_approve_for_agent_portal,
       u.cr_auto_approve_for_staff_portal, u.cr_auto_approve_for_partner
FROM "public"."g2p_register_sections" u
WHERE u.section_id = '01425f4e-720e-4a4e-a0db-73f371ae2a07'
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
