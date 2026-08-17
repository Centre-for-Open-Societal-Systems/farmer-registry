-- This UI release renders inactive tabs, so remove only the UI attachments and
-- tab definitions. Consent registers, sections, APIs, and records are retained.
DELETE FROM "public"."g2p_register_ui_tab_sections"
WHERE "tab_id" IN (
    'farmer_consent_requests_tab',
    'farmer_consent_receipts_tab'
);

DELETE FROM "public"."g2p_register_ui_tabs"
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd'
  AND "tab_id" IN (
      'farmer_consent_requests_tab',
      'farmer_consent_receipts_tab'
  );
