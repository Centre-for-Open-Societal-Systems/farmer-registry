-- Wording fixes for the Farmer register view and the Farmer registration form.
-- Display text only: no id, widget type, layout or validation changes. The
-- translation keys below override earlier seed values (this file sorts after
-- 80, 85, 86 and 87), so it is a merge of named keys where the new text wins;
-- the rest of the translation is left alone. Everything is idempotent.
-- 89_wording_fixes_checks.sql fails the seed if one of these reads the old
-- way again.

UPDATE "public"."registry_languages"
SET "domain_translation" = (COALESCE("domain_translation"::jsonb, '{}'::jsonb) ||
'{
 "fayda_fin_hint": "12-digit FIN or 16-digit FAN",
 "country_code": "Country (2-letter code)",
 "location_hierarchy": "Region, zone, woreda and kebele",
 "source_of_income": "Sources of income",
 "estimated_age": "Estimated age (years)",
 "date_must_be_past": "Choose today or an earlier date.",

 "bank_document": "Bank document",
 "farmer_document": "Farmer or cooperative document",
 "farmer_document_type": "Farmer or cooperative document type",
 "farmer_document_1": "Farmer or cooperative document 1",
 "farmer_document_2": "Farmer or cooperative document 2",
 "farmer_document_3": "Farmer or cooperative document 3",
 "farmer_document_4": "Farmer or cooperative document 4",
 "farmer_document_5": "Farmer or cooperative document 5",
 "land_document": "Land document",
 "representative_document": "Representative document",
 "other_document": "Other document",
 "other_document_purpose": "Purpose of other document",

 "is_household_head": "Is the farmer the head of the household?",
 "household_lookup_helptext": "Pick the household this farmer belongs to, if it is already registered. For a new household leave this empty; on the registration form, fill in the household information and household members below.",
 "farmer_household_lookup": "Household link",

 "is_primary_cooperative_member": "Member of a primary cooperative",
 "is_cooperative_union_member": "Member of a cooperative union",
 "is_farmer_cluster_member": "Member of a farmer cluster",

 "add_farm": "Add land",
 "unit": "Land size unit",

 "enumerator_name": "Name",
 "enumerator_user_id": "User ID",
 "data_collection_date": "Collected on",
 "enumerator_latitude": "Latitude when collected",
 "enumerator_longitude": "Longitude when collected",
 "enumerator_altitude": "Altitude when collected (m)",
 "enumerator_accuracy": "GPS accuracy when collected (m)",

 "farmer_lands": "Land records",
 "farmer_crops": "Crop records",
 "farmer_livestocks": "Livestock records",
 "farmer_farm_inputs": "Farm input records",
 "farmer_memberships": "Cooperative and cluster membership",
 "enumerator": "Enumerator details",

 "farmer_identity_verification": "Fayda ID verification",
 "farmer_land_summary": "Land summary",
 "farmer_livestock": "Livestock records",
 "farmer_membership": "Cooperative and cluster membership",
 "farmer_enumerator": "Enumerator details",
 "farmer_crops_intake": "Crop records",
 "farmer_farm_inputs_intake": "Farm input records",
 "farmer_livestock_intake": "Livestock records",

 "ethiopic_script_only": "Use Ethiopic (Ge''ez) script.",
 "phone_ethiopian_mobile": "Enter an Ethiopian mobile number, for example 0912345678 or +251912345678.",
 "land_size_positive": "Land size must be greater than 0.",
 "size_of_group_helptext": "Total members of the household: at least male + female members, and equal to the members listed below.",
 "is_head_helptext": "Tick for exactly one member: the household head.",
 "relationship_to_the_head_helptext": "Leave empty for the head (saved as self); required for every other member.",

 "land": "Land",
 "search_land": "Search land...",
 "select_land": "Select land",

 "INTAKE_FORM": "Intake form",
 "NEVER_ATTEND": "Never attended"
}'::jsonb)::json
WHERE "language_code" = 'en';

-- The land lookup on crop, livestock and farm-input rows carried literal
-- English ("Land", "Search land...", "Select land") instead of translation
-- keys. Same text, now translatable. Only the OAN-owned sections are touched.
UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(replace(replace(section_ui_schema::text,
  '"widget-label": "Land"', '"widget-label": "land"'),
  '"search_placeholder": "Search land..."', '"search_placeholder": "search_land"'),
  '"select_record_label": "Select land"', '"select_record_label": "select_land"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd'
  AND "section_id" IN ('farmer_crops', 'farmer_crops_intake', 'farmer_livestock', 'farmer_livestock_intake',
                       'farmer_farm_inputs', 'farmer_farm_inputs_intake');

-- The navigation entry and breadcrumb for the livestock register: livestock
-- is not countable.
UPDATE "public"."g2p_register_definitions" SET "register_subject" = 'Livestock'
WHERE "register_id" = '4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb';

-- Notes (a key is shared by every place that uses it):
-- country_code: the farmer location and the phone row both use this key, so
--   one text that reads right in both.
-- farmer_lands, farmer_crops, farmer_livestocks, farmer_farm_inputs,
--   farmer_memberships, enumerator, farmer_household_lookup: section titles.
--   The tab, the section and the table were all called the same ("Lands"
--   three times); the section now has its own name. The same key is the
--   section mnemonic that change-request and task lists print.
-- farmer_identity_verification .. farmer_livestock_intake: mnemonics of OAN
--   sections that had no text, so those lists printed the raw key.
-- Messages end with a full stop; the server strips it where it adds its own.
-- INTAKE_FORM: the source code the record history prints for the intake form.
-- NEVER_ATTEND: the ETH-OAN pack's display text.
