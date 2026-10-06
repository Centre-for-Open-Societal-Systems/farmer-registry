-- ODK submissions from the connector service become Farmer intakes.
--
-- The connector (openg2p-connector-service) polls ODK Central and posts each
-- submission to the Partner API as
--
--   POST /partner/ingest_data?data_model=FARMER_ODK_MODEL
--   {"header":  {"message_id": ..., "sender_id": "farmer-partner", "signature": ...},
--    "message": {"payload": {<the ODK submission, repeat groups expanded>,
--                            "register_mnemonic": "Farmer"}}}
--
-- The Partner API wraps the request as {"body": <request>}, so every path below
-- starts at $.body. From here the celery worker classifies the payload onto the
-- Farmer Ingestion Intake form, renders farmer_transform.j2 (odk/templates/,
-- uploaded to the templates bucket by db-seed) with the submission as
-- `expanded`, and creates the intake for approval.
--
-- These are the rows odk/setup_farmer_odk_connector.sql defines, with the same
-- ids, so an environment seeded by hand and one seeded here agree; db-seed now
-- applies them on every deploy. The partner itself lives in Master Data, which
-- db-seed does not write: see ci/connector/README.md, "Register the partner".
--
-- Every row is upserted on its fixed id, so a re-run changes nothing.

INSERT INTO "public"."data_models" (
    "data_model_id", "data_model_mnemonic", "pattern_for_data_model",
    "response_template_document_id", "is_active"
) VALUES (
    -- The DCI commons response template answers the connector.
    'FARMER_ODK_MODEL', 'FARMER_ODK_MODEL', '$.body.header.sender_id=>^.*$',
    '1f0953d4-f0fb-4336-a126-4d0519a74ffc', TRUE
) ON CONFLICT ("data_model_id") DO UPDATE SET
    "data_model_mnemonic" = EXCLUDED."data_model_mnemonic",
    "pattern_for_data_model" = EXCLUDED."pattern_for_data_model",
    "response_template_document_id" = EXCLUDED."response_template_document_id",
    "is_active" = EXCLUDED."is_active";

INSERT INTO "public"."incoming_model_key_paths" (
    "key_path_id", "data_model_id", "key_path_for_message_id", "key_path_for_sender",
    "key_path_for_signature", "key_path_for_signature_payload", "is_list",
    "key_path_for_list_elements"
) VALUES (
    'farmer_key_path', 'FARMER_ODK_MODEL',
    '$.body.header.message_id', '$.body.header.sender_id',
    '$.body.header.signature', '$.body.message', FALSE, ''
) ON CONFLICT ("key_path_id") DO UPDATE SET
    "data_model_id" = EXCLUDED."data_model_id",
    "key_path_for_message_id" = EXCLUDED."key_path_for_message_id",
    "key_path_for_sender" = EXCLUDED."key_path_for_sender",
    "key_path_for_signature" = EXCLUDED."key_path_for_signature",
    "key_path_for_signature_payload" = EXCLUDED."key_path_for_signature_payload",
    "is_list" = EXCLUDED."is_list",
    "key_path_for_list_elements" = EXCLUDED."key_path_for_list_elements";

-- Every connector submission is a new farmer: Farmer register, Farmer
-- Ingestion Intake form. The enricher passes the payload through unchanged.
INSERT INTO "public"."incoming_model_semantic_patterns" (
    "semantic_pattern_id", "data_model_id", "register_id", "intake_form_id",
    "section_id", "pattern_for_register", "pattern_for_intake_form",
    "pattern_for_section", "key_path_for_business_payload",
    "raw_payload_enricher_class"
) VALUES (
    'farmer_odk_semantic_pattern', 'FARMER_ODK_MODEL',
    'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-8782382649',
    NULL, NULL, '$.body.header.sender_id=>^.*$',
    NULL, '$.body.message.payload', 'G2PDciFarmerCreateEnricherService'
) ON CONFLICT ("semantic_pattern_id") DO UPDATE SET
    "data_model_id" = EXCLUDED."data_model_id",
    "register_id" = EXCLUDED."register_id",
    "intake_form_id" = EXCLUDED."intake_form_id",
    "pattern_for_intake_form" = EXCLUDED."pattern_for_intake_form",
    "key_path_for_business_payload" = EXCLUDED."key_path_for_business_payload",
    "raw_payload_enricher_class" = EXCLUDED."raw_payload_enricher_class";

-- The template catalogue row; the object itself is uploaded by db-seed
-- (LOAD_TEMPLATES) under the same key.
INSERT INTO "public"."g2p_registry_documents" (
    "document_id", "document_store_id", "bucket", "source_filename",
    "created_by", "created_at"
) VALUES (
    'farmer-odk-tmpl-doc', 'farmer_transform.j2', 'templates',
    'farmer_transform.j2', 'seeder', '2026-10-06 00:00:00'
) ON CONFLICT ("document_id") DO UPDATE SET
    "document_store_id" = EXCLUDED."document_store_id",
    "bucket" = EXCLUDED."bucket";

INSERT INTO "public"."incoming_templates" (
    "template_id", "register_id", "data_model_id", "template_document_id",
    "jsonld_expansion_required", "created_at", "updated_at"
) VALUES (
    'IN-TMPL-ODK', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',
    'FARMER_ODK_MODEL', 'farmer-odk-tmpl-doc',
    FALSE, '2026-10-06 00:00:00', NULL
) ON CONFLICT ("template_id") DO UPDATE SET
    "register_id" = EXCLUDED."register_id",
    "data_model_id" = EXCLUDED."data_model_id",
    "template_document_id" = EXCLUDED."template_document_id",
    "jsonld_expansion_required" = EXCLUDED."jsonld_expansion_required";
