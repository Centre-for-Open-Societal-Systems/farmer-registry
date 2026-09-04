INSERT INTO "public"."g2p_intake_form_definitions" ("form_id","register_id","form_mnemonic","form_description","number_of_verifications","used_only_in_ingestion_pipeline") VALUES 
('a1a4d25a-1cd4-4356-abac-8782382649','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','Farmer Ingestion Intake','Farmer Ingestion Intake',1,'TRUE'),
('9055ab43-c85d-4833-bd00-ca657bb72650','9055ab43-c85d-4833-bd00-ca657bb72644','Household Ingestion Intake','Household Ingestion Intake',1,'TRUE'),
-- G2R-73: staff-facing web intake form. Kept separate from the ingestion form above so that the
-- mandatory fields and format validation added in Phase 3 do not reject bulk-imported records.
('d3f1c7a0-4b62-4e19-9c85-6a1f2e0b7d41','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','Farmer Web Intake','Farmer registration via web intake form (G2R-73)',1,'FALSE');
