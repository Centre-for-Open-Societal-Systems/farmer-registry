INSERT INTO "public"."g2p_intake_form_ui_tabs" ("tab_id","form_id","tab_label","tab_order") VALUES
('a1a4d25a-1cd4-4356-abac-72482721','a1a4d25a-1cd4-4356-abac-8782382649','farmer_intake_tab',10),
('a1a4d25a-1cd4-4356-abac-72482725','a1a4d25a-1cd4-4356-abac-8782382649','farmer_consent_requests_intake_tab',80),
('a1a4d25a-1cd4-4356-abac-72482726','a1a4d25a-1cd4-4356-abac-8782382649','farmer_consent_receipts_intake_tab',85),
('a1a4d25a-1cd4-4356-abac-72482724','a1a4d25a-1cd4-4356-abac-8782382649','farmer_enumerator_intake_tab',95),
('9055ab43-c85d-4833-bd00-ca657bb72651','9055ab43-c85d-4833-bd00-ca657bb72650','household_intake_tab',10)
-- Upsert, not a bare INSERT: on an existing database a bare INSERT hits the
-- primary key and the WHOLE statement fails (db-seed runs with
-- ON_ERROR_STOP=0, so silently), and no row added or changed in this file
-- after the first seed ever reached that environment. The zz_*.sql files
-- still run after this and still win.
ON CONFLICT ("tab_id") DO UPDATE SET
    "form_id" = EXCLUDED."form_id",
    "tab_label" = EXCLUDED."tab_label",
    "tab_order" = EXCLUDED."tab_order";
