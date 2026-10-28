-- Fayda (eSignet) verification of a farmer's record, with the platform's own
-- id-authentication widget: it starts core's registrant authentication for
-- the record (register-data/authenticate_registrant with the esignet provider
-- that the chart provisions), opens eSignet in a popup, and shows the status,
-- date and expiry that core writes back (the register's authentication mixin,
-- register_domain/models). Core authenticates a register record,
-- so the section is on the farmer's record (20_layout.sql), not on the intake
-- form: the intake takes the typed ID, approval creates the record, and the
-- record is verified. A verified ID is then locked on the Identity section.
WITH sections (section_id, mnemonic, description, ui) AS (
  VALUES
  ('oan_farmer_identity_verification', 'oan_fr_farmer_identity_verification', 'Fayda verification of the farmer',
   '{"section-id": "farmer_identity_verification", "section-title": "identity_verification",
     "section-editable": false, "section-hide-edit-button": true, "section-column-span": 3,
     "panels": [{"panel-id": "oan_panel_identity_verification", "panel-orientation": "vertical", "panel-column-span": 3, "widgets": [
       {"widget": "id-authentication", "widget-id": "identity_verification", "widget-type": "group",
        "widget-label": "identity_verification", "widget-readonly": true,
        "widget-data-path": {
          "internalRecordId": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.internal_record_id",
          "foundationalId": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.foundational_id",
          "lastAuthenticatedOn": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.last_authenticated_at",
          "lastAuthenticationStatus": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.last_authentication_status",
          "expiryDate": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.authentication_expiry_at"},
        "widget-auth-config": {"service": "registry", "providerId": "esignet", "providerName": "eSignet",
          "registerId": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd",
          "authenticateEndpoint": "authenticate_registrant", "authenticateMethod": "POST",
          "useIframeOverlay": false, "popupWidth": 1024, "popupHeight": 800}}]}]}')
)
INSERT INTO "public"."g2p_register_sections" (
  "register_id", "section_id", "section_register_id", "is_core_section", "section_mnemonic",
  "section_description", "documents_required", "no_of_verifications_required", "is_list",
  "section_weightage", "section_ui_schema", "cr_auto_approve_for_bene_portal",
  "cr_auto_approve_for_agent_portal", "cr_auto_approve_for_staff_portal", "cr_auto_approve_for_partner")
SELECT 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', section_id, 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', false, mnemonic,
       description, false, 0, false, 0, ui::jsonb, false, false, false, false
FROM sections
ON CONFLICT ("section_id") DO UPDATE SET
  "register_id" = EXCLUDED."register_id", "section_register_id" = EXCLUDED."section_register_id",
  "section_mnemonic" = EXCLUDED."section_mnemonic", "section_description" = EXCLUDED."section_description",
  "is_list" = EXCLUDED."is_list", "section_weightage" = EXCLUDED."section_weightage",
  "section_ui_schema" = EXCLUDED."section_ui_schema";
