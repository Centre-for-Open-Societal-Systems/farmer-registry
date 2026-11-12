-- File import to the Farmer intake: the data model behind the native "Import
-- from file" menu (configuration: registry-configurations/g2p_registry_import_file_configurations.sql).
--
--   The import worker wraps every file row as
--   {"headers": {"message_id", "sender_id", "signature"}, "body": <flat row>}
--   and names the data model, the register and the intake form itself, so the
--   stage that classifies by pattern is skipped and the patterns below never
--   have to match.
--
-- The model has its own key paths, its own pattern with the identity
-- pass-through enricher (the Jinja template does all the mapping) and its own
-- template, farmer_file_import_intake.j2 (the farmer_ prefix because
-- the registries share one templates bucket). The ODK model
-- (odk_to_farmer_intake) is not used by file import and is not touched here.
--
-- This folder sorts after data-models/ and registry-inbound-message-rules/.
-- Idempotent: every row has a fixed id and is upserted.

INSERT INTO "public"."data_models" ("data_model_id","data_model_mnemonic","pattern_for_data_model","response_template_document_id","is_active") VALUES
('file_import_to_farmer_intake','FILE_IMPORT_TO_FARMER_INTAKE','$.headers.sender_id=>^Staff Portal$',NULL,TRUE)
ON CONFLICT ("data_model_id") DO UPDATE SET
    "data_model_mnemonic" = EXCLUDED."data_model_mnemonic",
    "pattern_for_data_model" = EXCLUDED."pattern_for_data_model",
    "is_active" = EXCLUDED."is_active";

INSERT INTO "public"."incoming_model_key_paths" (
    "key_path_id","data_model_id","key_path_for_message_id","key_path_for_sender",
    "key_path_for_signature","key_path_for_signature_payload","is_list","key_path_for_list_elements"
) VALUES
('file_import_to_farmer_intake_key_path','file_import_to_farmer_intake','$.headers.message_id','$.headers.sender_id','$.headers.signature','$.body','FALSE','')
ON CONFLICT ("key_path_id") DO UPDATE SET
    "data_model_id" = EXCLUDED."data_model_id",
    "key_path_for_message_id" = EXCLUDED."key_path_for_message_id",
    "key_path_for_sender" = EXCLUDED."key_path_for_sender",
    "key_path_for_signature" = EXCLUDED."key_path_for_signature",
    "key_path_for_signature_payload" = EXCLUDED."key_path_for_signature_payload",
    "is_list" = EXCLUDED."is_list",
    "key_path_for_list_elements" = EXCLUDED."key_path_for_list_elements";

-- The business payload is the flat row; the enricher is the identity pass-through.
INSERT INTO "public"."incoming_model_semantic_patterns" (
    "semantic_pattern_id","data_model_id","register_id","intake_form_id",
    "pattern_for_register","pattern_for_intake_form","key_path_for_business_payload","raw_payload_enricher_class"
) VALUES
('file_import_to_farmer_intake_pattern','file_import_to_farmer_intake','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','a1a4d25a-1cd4-4356-abac-8782382649','$.headers.sender_id=>^.+$','$.headers.sender_id=>^NEVER_CLASSIFY$','$.body','G2PPassThroughEnricherService')
ON CONFLICT ("semantic_pattern_id") DO UPDATE SET
    "data_model_id" = EXCLUDED."data_model_id",
    "register_id" = EXCLUDED."register_id",
    "intake_form_id" = EXCLUDED."intake_form_id",
    "pattern_for_register" = EXCLUDED."pattern_for_register",
    "pattern_for_intake_form" = EXCLUDED."pattern_for_intake_form",
    "key_path_for_business_payload" = EXCLUDED."key_path_for_business_payload",
    "raw_payload_enricher_class" = EXCLUDED."raw_payload_enricher_class";

-- The template catalogue row; the image carries the file in the templates
-- bucket under the same name.
INSERT INTO "public"."g2p_registry_documents" ("document_id","document_store_id","bucket","source_filename","created_by","created_at") VALUES
('file_import_to_farmer_intake_document','farmer_file_import_intake.j2','templates','farmer_file_import_intake.j2','seeder','2026-11-12 00:00:00')
ON CONFLICT ("document_id") DO UPDATE SET
    "document_store_id" = EXCLUDED."document_store_id",
    "bucket" = EXCLUDED."bucket",
    "source_filename" = EXCLUDED."source_filename";

INSERT INTO "public"."incoming_templates" ("template_id","register_id","data_model_id","template_document_id","jsonld_expansion_required","created_at","updated_at") VALUES
('file_import_to_farmer_intake_template','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','file_import_to_farmer_intake','file_import_to_farmer_intake_document','FALSE','2026-11-12 00:00:00',NULL)
ON CONFLICT ("template_id") DO UPDATE SET
    "register_id" = EXCLUDED."register_id",
    "data_model_id" = EXCLUDED."data_model_id",
    "template_document_id" = EXCLUDED."template_document_id",
    "jsonld_expansion_required" = EXCLUDED."jsonld_expansion_required";
