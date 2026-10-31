-- What the Farmer registry gives Crop and Livestock (templates under
-- oan-extension/templates/, uploaded by the seed with LOAD_TEMPLATES=true).
--
-- 1. The DCI search response: the farmer extension's template with the
--    farmer_reference block added as its last object (farmer_dci_search_response.j2).
--    Partners read it through the signed,
--    consent-checked DCI search; the Consent Manager scope "farmer_reference"
--    releases that block only.
-- 2. The change notice: on every approved farmer change, outgestion publishes
--    farmer_reference.changed.v1 (farmer id and Fayda ID, no personal details)
--    to the WebSub topic oan.farmer-reference.changed.v1.
--
-- The data model (id and mnemonic FARMER_REFERENCE_CHANGED_V1), the event type
-- and the topic name are what Crop and Livestock subscribe to
-- (integrations/farmer-reference/config.yaml). The document, template and topic
-- rows are this registry's own and are named after the flow they serve.

INSERT INTO "public"."g2p_registry_documents" ("document_id","document_store_id","bucket","source_filename","created_by","created_at") VALUES
('farmer_dci_search_response_document','farmer_dci_search_response.j2','templates','farmer_dci_search_response.j2','seeder','2026-10-25 00:00:00'),
('farmer_reference_changed_v1_document','farmer_reference_changed_v1.j2','templates','farmer_reference_changed_v1.j2','seeder','2026-10-25 00:00:00')
ON CONFLICT ("document_id") DO UPDATE SET "document_store_id" = EXCLUDED."document_store_id", "bucket" = EXCLUDED."bucket", "source_filename" = EXCLUDED."source_filename";

-- The farmer extension seeds OUT-TMPL-1 with its own document; the OAN layer
-- runs after it and points the Farmer DCI response at OAN's.
UPDATE "public"."outgoing_templates" SET "template_document_id" = 'farmer_dci_search_response_document'
WHERE "template_id" = 'OUT-TMPL-1' AND "template_document_id" IS DISTINCT FROM 'farmer_dci_search_response_document';

INSERT INTO "public"."data_models" ("data_model_id","data_model_mnemonic","pattern_for_data_model","response_template_document_id","is_active") VALUES
('873c2342-cfde-5db4-9f9f-6e491a5001f7','FARMER_REFERENCE_CHANGED_V1','$.body.message.payload.event_type=>^farmer_reference[.]changed[.]v1$',NULL,TRUE)
ON CONFLICT ("data_model_id") DO UPDATE SET "data_model_mnemonic" = EXCLUDED."data_model_mnemonic", "pattern_for_data_model" = EXCLUDED."pattern_for_data_model", "is_active" = EXCLUDED."is_active";

INSERT INTO "public"."outgoing_templates" ("template_id","data_model_id","register_id","template_document_id","created_at","updated_at") VALUES
('farmer_reference_changed_v1_template','873c2342-cfde-5db4-9f9f-6e491a5001f7','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','farmer_reference_changed_v1_document','2026-10-25 00:00:00',NULL)
ON CONFLICT ("template_id") DO UPDATE SET "data_model_id" = EXCLUDED."data_model_id", "register_id" = EXCLUDED."register_id", "template_document_id" = EXCLUDED."template_document_id";

-- The WebSub registration state belongs to the outgestion worker; a re-seed
-- keeps the complete installed topic configuration and worker state. Existing
-- activation/topic settings belong to the environment; do not force-enable a
-- disabled topic or rewrite its registration/checkpoint values during a seed.
INSERT INTO "public"."outgoing_topics" ("topic_id","topic_type","register_id","data_model_id","partner_id","websub_topic","description","is_active","created_at","websub_register_status","websub_register_number_of_attempts") VALUES
('farmer_reference_changed_v1_topic','REGISTER','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','873c2342-cfde-5db4-9f9f-6e491a5001f7',NULL,'oan.farmer-reference.changed.v1','Approved farmer changes, for the registries that keep a Farmer reference',TRUE,'2026-10-25 00:00:00','PENDING',0)
ON CONFLICT ("topic_id") DO NOTHING;

-- Outgestion runs for the Farmer register only.
UPDATE "public"."g2p_register_definitions" SET "outgest_applicable" = TRUE
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND NOT "outgest_applicable";
