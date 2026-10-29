-- When a request does not name its data model, the platform tries every row's
-- pattern, so each pattern must be "<jsonpath>=><regex>": a bare "*" makes the
-- matcher raise "Invalid pattern format" and the ingest fails with SYS-ERR-001.
-- The pattern is part of the upsert so a database seeded with "*" is repaired
-- by a plain upgrade.
INSERT INTO "public"."data_models" ("data_model_id","data_model_mnemonic","pattern_for_data_model","response_template_document_id","is_active") VALUES
('c331ba96-ac35-4014-9d13-4ef327f6b79b','DCI','$.body.header.data_model=>^DCI$','1f0953d4-f0fb-4336-a126-4d0519a74ffc','TRUE')
ON CONFLICT ("data_model_id") DO UPDATE SET "data_model_mnemonic" = EXCLUDED."data_model_mnemonic", "pattern_for_data_model" = EXCLUDED."pattern_for_data_model", "response_template_document_id" = EXCLUDED."response_template_document_id", "is_active" = EXCLUDED."is_active";

-- DCI response template: dci_commons_response.json.j2
