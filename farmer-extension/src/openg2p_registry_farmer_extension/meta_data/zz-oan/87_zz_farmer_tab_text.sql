-- Text for the Farmer tab's header and identity fields: the header captions
-- (11_header_section.sql), the Ethiopian-calendar birth date and the hint under
-- the Fayda ID. Named translation keys merged over the earlier seed values, so
-- the text here wins and the statement is idempotent. It sorts after the other
-- 87_ files and before 88_readable_text_checks.sql, which reads the final text.

UPDATE "public"."registry_languages"
SET "domain_translation" = (COALESCE("domain_translation"::jsonb, '{}'::jsonb) ||
'{
 "farmer_header_farmer_id": "Farmer ID",
 "farmer_header_status": "Status",
 "farmer_header_status_reason": "Reason for status",
 "farmer_header_created_by": "Created by",
 "farmer_header_created_on": "Created on",
 "farmer_header_last_approved_by": "Last approved by",
 "farmer_header_last_approved_on": "Last approved on",
 "birth_date_ec": "Birth date (Ethiopian calendar)",
  "farmer_map_pin": "Pin on map",
 "fayda_verification_status": "Verification status",
 "fayda_id_help": "A 12-digit number is a FIN and a 16-digit number is a FAN."
}'::jsonb)::json
WHERE "language_code" = 'en';
