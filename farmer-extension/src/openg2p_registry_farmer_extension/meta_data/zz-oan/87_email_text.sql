-- Text for the farmer's email address section (15_sections.sql, farmer_email).
-- A merge of named keys where this text wins, so it is idempotent and reaches
-- a registry seeded before it. Only English is carried by the seed: the
-- registry has no other language for the OAN labels.

UPDATE "public"."registry_languages"
SET "domain_translation" = (COALESCE("domain_translation"::jsonb, '{}'::jsonb) ||
'{
 "farmer_email": "Email",
 "email": "Email address",
 "email_format": "Enter an address like name@example.org"
}'::jsonb)::json
WHERE "language_code" = 'en';
