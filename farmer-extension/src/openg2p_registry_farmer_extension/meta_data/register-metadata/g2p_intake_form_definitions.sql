INSERT INTO "public"."g2p_intake_form_definitions" ("form_id","register_id","form_mnemonic","form_description","number_of_verifications","used_only_in_ingestion_pipeline") VALUES 
('a1a4d25a-1cd4-4356-abac-8782382649','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','Farmer Ingestion Intake','Farmer Registration',1,'TRUE'),
('9055ab43-c85d-4833-bd00-ca657bb72650','9055ab43-c85d-4833-bd00-ca657bb72644','Household Ingestion Intake','Household Ingestion Intake',1,'TRUE')
-- Upsert, not a bare INSERT: on an existing database a bare INSERT hits the
-- primary key and the WHOLE statement fails (db-seed runs with
-- ON_ERROR_STOP=0, so silently), and no row added or changed in this file
-- after the first seed ever reached that environment. The zz_*.sql files
-- still run after this and still win.
ON CONFLICT ("form_id") DO UPDATE SET
    "register_id" = EXCLUDED."register_id",
    "form_mnemonic" = EXCLUDED."form_mnemonic",
    "form_description" = EXCLUDED."form_description",
    "number_of_verifications" = EXCLUDED."number_of_verifications",
    "used_only_in_ingestion_pipeline" = EXCLUDED."used_only_in_ingestion_pipeline";
