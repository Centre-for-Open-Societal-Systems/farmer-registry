-- Readable text, fourth pass: the labels the deploy 126 re-check still found
-- unclear. Display text only; no id, code, path or validation changes. Each
-- wording follows what the field holds (see the comment on each key). A merge
-- of named translation keys plus one explicit-id UPDATE, so it is idempotent.
-- It sorts after 87_readable_remaining_text.sql and wins over 80 and 86;
-- 88_readable_text_checks.sql fails the seed if one of these reads the old way.

UPDATE "public"."registry_languages"
SET "domain_translation" = (COALESCE("domain_translation"::jsonb, '{}'::jsonb) ||
'{
 "other_land_owner": "Another land owner in the household",
 "required_household_fields": "Household size, male/female counts and another land owner in the household are required",
 "enumerator_accuracy": "Enumerator GPS accuracy (metres)",
 "enumerator_altitude": "Enumerator altitude (metres)",
 "farmer_document": "Farmer or cooperative membership document",
 "total_land_crop_sharing_area": "Crop-sharing or other land (ha)",
 "Intake Form": "Intake form",
 "skipped": "Not needed (decided by another approver)"
}'::jsonb)::json
WHERE "language_code" = 'en';

-- other_land_owner: Yes/No, whether anyone else in the household owns land.
-- enumerator_accuracy: the GPS accuracy, in metres, of the enumerator's position.
-- farmer_document: the document that shows a person is a farmer or a member of a
--   farmer organisation (the FARMER_DOCUMENT_TYPE list).
-- total_land_crop_sharing_area: the land that is neither owned nor rented (the
--   land roll-up counts every parcel that is not OWNER or TENANT here), so the
--   label says "or other land".
-- "Intake Form": the record history's source column prints this stored value.
-- skipped: a task decided by another approver, so this one is not needed.

-- The navigation entry and breadcrumb for the score register.
UPDATE "public"."g2p_register_definitions" SET "register_subject" = 'Household scores'
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-638239923092';
