-- OAN's own register: the farmer's phone numbers, a child TABLE register of the
-- Farmer defined the way the farmer seed defines Land or Livestock. Its tables
-- are created by the OAN initializer (app.py, OAN_REGISTERS), its section is in
-- 15_sections.sql. The id is the previous farmer registry's.
--
-- The farmer's identifiers are not a register or a section: the Fayda FIN is
-- upstream's foundational_id, and the RID, ODK Farmer ID and Pula ID are
-- attributes of the farmer, asked in personal identification (10_sections.sql).

INSERT INTO "public"."g2p_register_definitions" (
  "register_id", "register_mnemonic", "register_subject", "register_description", "master_register_id",
  "register_rank", "functional_id_generation_required", "register_purpose", "program_id", "program_mnemonic",
  "register_icon", "has_image", "dedup_is_enabled", "dedup_threshold_score", "completion_score_required",
  "outgest_applicable", "requires_registrant_authentication", "registrant_authentication_validity_days",
  "registrant_re_auth_warning_days_before")
VALUES
  ('c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f', 'FarmerPhone', 'Farmer Phones', 'Farmer Phone Register',
   'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 12, false, 'TABLE', NULL, NULL, NULL, false, false, 0, false,
   false, false, 730, 30)
ON CONFLICT ("register_id") DO UPDATE SET
  "register_mnemonic" = EXCLUDED."register_mnemonic", "register_subject" = EXCLUDED."register_subject",
  "register_description" = EXCLUDED."register_description", "master_register_id" = EXCLUDED."master_register_id",
  "register_rank" = EXCLUDED."register_rank", "register_purpose" = EXCLUDED."register_purpose";

INSERT INTO "public"."g2p_register_schemas" ("register_id", "deduplicate_schema", "search_result_schema", "filter_schema")
VALUES
  ('c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f', '[]',
   '[{"field_name": "phone_type", "display_label": "Phone Type", "order": 1},
     {"field_name": "phone_number", "display_label": "Phone Number", "order": 2},
     {"field_name": "is_primary", "display_label": "Primary", "order": 3}]',
   '[{"field_name": "phone_number", "display_label": "Phone Number", "filter_type": "text", "order": 1, "allowed_operators": ["eq", "contains"]}]')
ON CONFLICT ("register_id") DO UPDATE SET
  "deduplicate_schema" = EXCLUDED."deduplicate_schema", "search_result_schema" = EXCLUDED."search_result_schema",
  "filter_schema" = EXCLUDED."filter_schema";

-- The farmer list shows where each farmer lives. The names are derived from
-- the farmer's location (register_domain/derived.py). Upstream's columns are
-- kept, and these are appended once.
UPDATE "public"."g2p_register_schemas" s
SET "search_result_schema" = (s."search_result_schema"::jsonb || (
  SELECT COALESCE(jsonb_agg(jsonb_build_object('field_name', f, 'display_label', l, 'order', 100 + o) ORDER BY o), '[]'::jsonb)
  FROM (VALUES (1, 'region_name', 'Region'), (2, 'zone_name', 'Zone'), (3, 'woreda_name', 'Woreda'), (4, 'kebele_name', 'Kebele')) v(o, f, l)
  WHERE NOT EXISTS (SELECT 1 FROM json_array_elements(s."search_result_schema") e WHERE e->>'field_name' = v.f)))::json
WHERE s."register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';

-- A farmer's record is verified with Fayda (eSignet): core's registrant
-- authentication, started by the platform's id-authentication widget on the
-- record (18_identity_verification.sql). The provider itself (client id, key,
-- callback URL) is deployment data in g2p_registrant_authentication_providers,
-- provisioned by the chart; see the README.
-- This flag enables the widget; it is not a finalize verification gate.
UPDATE "public"."g2p_register_definitions"
SET "requires_registrant_authentication" = true
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';
