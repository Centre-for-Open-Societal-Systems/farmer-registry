-- Readable text, third pass: what the deploy 124 re-check of the Farmer registry
-- still found. Display text only; no id, code, path or validation changes.
-- Every statement is a merge of named translation keys or an UPDATE of named
-- register schemas, so it is idempotent. It sorts after 86_readable_screen_text.sql
-- and wins over it; 88_readable_text_checks.sql fails the seed if one of these
-- reads the old way.
--
-- Not done here, because the staff UI (platform) owns it: the register list's
-- desktop table prints stored values without a lookup, and its column headers
-- are Title Cased by the table widget.

-- Platform screen text. The staff UI looks these two up as flat dotted keys; the
-- nested "common" block of the language row is not what it reads.
UPDATE "public"."registry_languages"
SET "core_translation" = (COALESCE("core_translation"::jsonb, '{}'::jsonb) ||
'{
 "common.remove": "Remove",
 "common.select": "Select"
}'::jsonb)::json
WHERE "language_code" = 'en';

-- Domain text (English)
UPDATE "public"."registry_languages"
SET "domain_translation" = (COALESCE("domain_translation"::jsonb, '{}'::jsonb) ||
'{
 "identity_document_1": "Identity document 1",
 "identity_document_2": "Identity document 2",
 "identity_document_3": "Identity document 3",
 "identity_document_4": "Identity document 4",
 "identity_document_5": "Identity document 5",
 "bank_document_1": "Bank document 1",
 "bank_document_2": "Bank document 2",
 "bank_document_3": "Bank document 3",
 "bank_document_4": "Bank document 4",
 "bank_document_5": "Bank document 5",
 "land_document_1": "Land document 1",
 "land_document_2": "Land document 2",
 "land_document_3": "Land document 3",
 "land_document_4": "Land document 4",
 "land_document_5": "Land document 5",
 "representative_document_1": "Representative document 1",
 "representative_document_2": "Representative document 2",
 "representative_document_3": "Representative document 3",
 "representative_document_4": "Representative document 4",
 "representative_document_5": "Representative document 5",
 "farmer_document_1": "Farmer document 1",
 "farmer_document_2": "Farmer document 2",
 "farmer_document_3": "Farmer document 3",
 "farmer_document_4": "Farmer document 4",
 "farmer_document_5": "Farmer document 5",
 "other_document_1": "Other document 1",
 "other_document_2": "Other document 2",
 "other_document_3": "Other document 3",
 "other_document_4": "Other document 4",
 "other_document_5": "Other document 5",
 "fayda_fin": "Fayda ID (FAN or FIN)",
 "foundational_id": "Fayda ID (FAN or FIN)",
 "FAYDA": "Fayda ID (FAN or FIN)",
 "fayda_fin_format": "Enter the Fayda ID as a 12-digit FIN or a 16-digit FAN, using digits only. Verification is optional; upload ID evidence for approval.",
 "disabled": "Has a disability",
 "is_diseased": "Affected by disease or pests",
 "size_of_group": "Household size",
 "required_household_fields": "Household size, male/female counts and other land owner are required",
 "is_primary": "Primary phone number",
 "location_hierarchy": "Administrative hierarchy",
 "plus_code": "Plus code (map location)",
 "computation_scores": "Poverty score",
 "household_computation_scores": "Poverty score",
 "approver": "Approval",
 "in_review": "In review",
 "request_created": "Request created",
 "request_approved": "Request approved",
 "stage_started": "Stage started",
 "stage_completed": "Stage completed",
 "completed": "Completed",
 "skipped": "Skipped"
}'::jsonb)::json
WHERE "language_code" = 'en';

-- Register list headers (search result and filter schemas) that carry literal
-- text instead of a key.
UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace("search_result_schema"::jsonb::text, '"display_label": "Size of group"', '"display_label": "Household size"')::json,
    "filter_schema" = replace("filter_schema"::jsonb::text, '"display_label": "Size of group"', '"display_label": "Household size"')::json
WHERE "register_id" = '9055ab43-c85d-4833-bd00-ca657bb72644';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace("search_result_schema"::jsonb::text, '"display_label": "Primary"', '"display_label": "Primary phone number"')::json
WHERE "register_id" = 'c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f';
