INSERT INTO "public"."g2p_register_ui_tabs" ("tab_id","register_id","tab_label","tab_order","is_active") VALUES 
('household_farmer_tab','9055ab43-c85d-4833-bd00-ca657bb72644','household_farmer_tab',2,'TRUE'),
('household_household_tab','9055ab43-c85d-4833-bd00-ca657bb72644','household_household_tab',1,'TRUE'),
('farmer_farmer_tab','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','farmer_farmer_tab',0,'TRUE'),
('farmer_household_link_tab','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','farmer_household_link_tab',2,'TRUE'),
('farmer_location_tab','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','farmer_location_tab',5,'TRUE'),
('farmer_ids_tab','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','farmer_ids_tab',35,'TRUE'),
('farmer_consent_requests_tab','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','farmer_consent_requests_tab',36,'TRUE'),
('farmer_consent_receipts_tab','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','farmer_consent_receipts_tab',38,'TRUE'),
('farmer_enumerator_tab','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','farmer_enumerator_tab',40,'TRUE'),
('farmer_crop_tab','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','farmer_crops_tab',20,'TRUE'),
('farmer_livestock_tab','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','farmer_livestocks_tab',25,'TRUE'),
('farmer_land_tab','a1a4d25a-1cd4-4356-abac-985a0b3c6bcd','farmer_lands_tab',15,'TRUE')
-- Upsert, not a bare INSERT: on an existing database a bare INSERT hits the
-- primary key and the WHOLE statement fails (db-seed runs with
-- ON_ERROR_STOP=0, so silently), and no row added or changed in this file
-- after the first seed ever reached that environment. The zz_*.sql files
-- still run after this and still win.
ON CONFLICT ("tab_id") DO UPDATE SET
    "register_id" = EXCLUDED."register_id",
    "tab_label" = EXCLUDED."tab_label",
    "tab_order" = EXCLUDED."tab_order",
    "is_active" = EXCLUDED."is_active";
