-- Readable text: the last pass over what staff read in the Farmer registry.
--
-- Plain English in sentence case, no underscores or internal keys, and no
-- abbreviation that is not spelled out (ID, FAN, FIN and GPS stay). Only
-- display text changes; translation keys, ids, codes and mnemonics do not.
-- The location widgets, which carried literal English, now name translation
-- keys so a language can translate them. Every statement is an explicit-id
-- UPDATE or a merge of named translation keys, so it is idempotent. It sorts
-- after 80_label_casing.sql and so wins over it; 88_readable_text_checks.sql
-- fails the seed if a visible label or choice reads like a code.

-- Display labels: domain translations (English)
UPDATE "public"."registry_languages"
SET "domain_translation" = (COALESCE("domain_translation"::jsonb, '{}'::jsonb) ||
'{
 "farmer_personal_details": "Personal information",
 "personal_information": "Personal information",
 "id_authentication": "ID authentication",
 "socio_economic_and_health": "Socio-economic and health details",
 "farmer_socio_economic_and_health": "Socio-economic and health",
 "household_socio_economic_and_health": "Farmer socio-economic and health",
 "fr_farmer_socio_and_health": "Socio-economic and health",
 "hh_farmer_socio_and_health": "Farmer socio-economic and health",
 "socio_economic_details": "Socio-economic details",
 "household_members_records": "Household member records",
 "farmer_registry": "Farmer registry",
 "Farmer Registry": "Farmer registry",
 "farmer_ingestion_intake": "Farmer registration",
 "household_ingestion_intake": "Household registration",
 "fayda_rid": "Fayda ID registration number",
 "fayda_rid_format": "The Fayda ID registration number has 29 digits. Enter all 29, digits only, as printed on the registration slip.",
 "odk_farmer_id": "Survey farmer ID (ODK)",
 "is_psnp_user": "Productive Safety Net Programme beneficiary",
 "is_head": "Head of household",
 "livestocks": "Livestock",
 "fr_farmer_livestocks": "Livestock",
 "local_language": "Local language",
 "name_letters_only": "Use letters only. Spaces, apostrophes and hyphens are allowed, up to 100 characters. Remove digits and other symbols.",
 "finance_access_type": "Finance access type",
 "fayda_fin_hint": "12 or 16 digits",
 "location_hierarchy": "Location hierarchy",
 "plus_code": "Plus code",
 "plus_code_format": "Enter a valid plus code, for example 35AB+14 or 8FVC9G8F+6W.",
 "country_code_format": "Enter the 2-letter country code, for example ET for Ethiopia.",
 "SEMI_NOMADIC": "Semi-nomadic",
 "WELL_GROUND_WATER": "Well (ground water)",
 "IRRIGATION_GROUND_WATER": "Irrigation from ground water",
 "IRRIGATION_SURFACE_WATER": "Irrigation from surface water",
 "DONATION_GIFT": "Donation or gift",
 "RENTING_LEASING": "Renting or leasing",
 "GOVERNMENT_NGO_SUPPORT": "Government or non-governmental organisation support",
 "SOI_GOVERNMENT_NGO_SUPPORT": "Government or non-governmental organisation support",
 "SOI_OTHERS": "Other",
 "OTHERS": "Other",
 "NON_RELATIVE": "Non-relative"
}'::jsonb)::json
WHERE "language_code" = 'en';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(section_ui_schema::text, '"widget-label": "Location hierarchy"', '"widget-label": "location_hierarchy"'), '"widget-label": "Address line 1"', '"widget-label": "address_line_1"'), '"widget-label": "Address line 2"', '"widget-label": "address_line_2"'), '"widget-label": "Postal code"', '"widget-label": "postal_code"'), '"widget-label": "Country code"', '"widget-label": "country_code"'), '"widget-label": "Plus code"', '"widget-label": "plus_code"'), '"widget-label": "Latitude"', '"widget-label": "latitude"'), '"widget-label": "Longitude"', '"widget-label": "longitude"'), '"widget-label": "Altitude"', '"widget-label": "altitude"'), '"patternMessage": "Enter a 2-letter country code (for example KM)"', '"patternMessage": "country_code_format"'), '"patternMessage": "Enter a valid plus code (for example 35AB+14 or 8FVC9G8F+6W)"', '"patternMessage": "plus_code_format"')::jsonb
WHERE "section_id" = 'farmer_farmer_location_section_03';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(section_ui_schema::text, '"widget-label": "Location hierarchy"', '"widget-label": "location_hierarchy"'), '"widget-label": "Address line 1"', '"widget-label": "address_line_1"'), '"widget-label": "Address line 2"', '"widget-label": "address_line_2"'), '"widget-label": "Postal code"', '"widget-label": "postal_code"'), '"widget-label": "Country code"', '"widget-label": "country_code"'), '"widget-label": "Plus code"', '"widget-label": "plus_code"'), '"widget-label": "Latitude"', '"widget-label": "latitude"'), '"widget-label": "Longitude"', '"widget-label": "longitude"'), '"widget-label": "Altitude"', '"widget-label": "altitude"'), '"patternMessage": "Enter a 2-letter country code (for example KM)"', '"patternMessage": "country_code_format"'), '"patternMessage": "Enter a valid plus code (for example 35AB+14 or 8FVC9G8F+6W)"', '"patternMessage": "plus_code_format"')::jsonb
WHERE "section_id" = 'farmer_household_location_section_03';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(section_ui_schema::text, '"widget-label": "Location hierarchy"', '"widget-label": "location_hierarchy"'), '"widget-label": "Address line 1"', '"widget-label": "address_line_1"'), '"widget-label": "Address line 2"', '"widget-label": "address_line_2"'), '"widget-label": "Postal code"', '"widget-label": "postal_code"'), '"widget-label": "Country code"', '"widget-label": "country_code"'), '"widget-label": "Plus code"', '"widget-label": "plus_code"'), '"widget-label": "Latitude"', '"widget-label": "latitude"'), '"widget-label": "Longitude"', '"widget-label": "longitude"'), '"widget-label": "Altitude"', '"widget-label": "altitude"'), '"patternMessage": "Enter a 2-letter country code (for example KM)"', '"patternMessage": "country_code_format"'), '"patternMessage": "Enter a valid plus code (for example 35AB+14 or 8FVC9G8F+6W)"', '"patternMessage": "plus_code_format"')::jsonb
WHERE "section_id" = 'farmer_location';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(section_ui_schema::text, '"widget-label": "Location hierarchy"', '"widget-label": "location_hierarchy"'), '"widget-label": "Address line 1"', '"widget-label": "address_line_1"'), '"widget-label": "Address line 2"', '"widget-label": "address_line_2"'), '"widget-label": "Postal code"', '"widget-label": "postal_code"'), '"widget-label": "Country code"', '"widget-label": "country_code"'), '"widget-label": "Plus code"', '"widget-label": "plus_code"'), '"widget-label": "Latitude"', '"widget-label": "latitude"'), '"widget-label": "Longitude"', '"widget-label": "longitude"'), '"widget-label": "Altitude"', '"widget-label": "altitude"'), '"patternMessage": "Enter a 2-letter country code (for example KM)"', '"patternMessage": "country_code_format"'), '"patternMessage": "Enter a valid plus code (for example 35AB+14 or 8FVC9G8F+6W)"', '"patternMessage": "plus_code_format"')::jsonb
WHERE "section_id" = 'household_farmer_location_section_03';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(section_ui_schema::text, '"widget-label": "Location hierarchy"', '"widget-label": "location_hierarchy"'), '"widget-label": "Address line 1"', '"widget-label": "address_line_1"'), '"widget-label": "Address line 2"', '"widget-label": "address_line_2"'), '"widget-label": "Postal code"', '"widget-label": "postal_code"'), '"widget-label": "Country code"', '"widget-label": "country_code"'), '"widget-label": "Plus code"', '"widget-label": "plus_code"'), '"widget-label": "Latitude"', '"widget-label": "latitude"'), '"widget-label": "Longitude"', '"widget-label": "longitude"'), '"widget-label": "Altitude"', '"widget-label": "altitude"'), '"patternMessage": "Enter a 2-letter country code (for example KM)"', '"patternMessage": "country_code_format"'), '"patternMessage": "Enter a valid plus code (for example 35AB+14 or 8FVC9G8F+6W)"', '"patternMessage": "plus_code_format"')::jsonb
WHERE "section_id" = 'household_household_location_section_03';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"widget-data-placeholder": "12 or 16 digits"', '"widget-data-placeholder": "fayda_fin_hint"')::jsonb
WHERE "section_id" = 'farmer_identity';

UPDATE "public"."g2p_register_schemas"
SET "filter_schema" = replace(replace(replace("filter_schema"::jsonb::text, '"display_label": "Birthdate"', '"display_label": "Birth date"'), '"display_label": "Last name"', '"display_label": "Grandfather''s name"'), '"label": "Others"', '"label": "Other"')::json
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace("search_result_schema"::jsonb::text, '"display_label": "Last name"', '"display_label": "Grandfather''s name"')::json
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';

UPDATE "public"."g2p_register_schemas"
SET "filter_schema" = replace(replace(replace("filter_schema"::jsonb::text, '"display_label": "Is head"', '"display_label": "Head of household"'), '"display_label": "Is disabled"', '"display_label": "Has a disability"'), '"label": "Non relative"', '"label": "Non-relative"')::json
WHERE "register_id" = '52979fdd-220c-48dd-8de0-0a434e786427';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace(replace("search_result_schema"::jsonb::text, '"display_label": "Is head"', '"display_label": "Head of household"'), '"display_label": "Is disabled"', '"display_label": "Has a disability"')::json
WHERE "register_id" = '52979fdd-220c-48dd-8de0-0a434e786427';

-- What each register holds, as the registers list says it

UPDATE "public"."g2p_register_definitions" SET "register_description" = 'Land parcels that farmers hold' WHERE "register_id" = '493153d5-07ef-4743-8efd-07f4099772b9';

UPDATE "public"."g2p_register_definitions" SET "register_description" = 'Livestock that farmers keep' WHERE "register_id" = '4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb';

UPDATE "public"."g2p_register_definitions" SET "register_description" = 'Crops that farmers grow' WHERE "register_id" = '5fa096f8-ffdc-4b0a-ab16-9ca386c23310';

UPDATE "public"."g2p_register_definitions" SET "register_description" = 'Scores worked out for households' WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-638239923092';

UPDATE "public"."g2p_register_definitions" SET "register_description" = 'Households that farmers belong to' WHERE "register_id" = '9055ab43-c85d-4833-bd00-ca657bb72644';

UPDATE "public"."g2p_register_definitions" SET "register_description" = 'Registered farmers, with their identity, household, land, crops, livestock and membership' WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';

UPDATE "public"."g2p_register_definitions" SET "register_description" = 'The members of each household' WHERE "register_id" = '52979fdd-220c-48dd-8de0-0a434e786427';

UPDATE "public"."g2p_register_definitions" SET "register_description" = 'Phone numbers of farmers' WHERE "register_id" = 'c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f';

UPDATE "public"."g2p_register_definitions" SET "register_description" = 'Fertilizer, pesticide, seed and water use on farms' WHERE "register_id" = '18df8370-3e9a-493f-aa27-fc1b9e05629c';

UPDATE "public"."g2p_register_definitions" SET "register_description" = 'Cooperative and farmer cluster membership' WHERE "register_id" = '495f251c-83a5-4025-a307-1925712c9d0b';


UPDATE "public"."g2p_intake_form_definitions" SET "form_description" = 'Farmer registration' WHERE "form_id" = 'a1a4d25a-1cd4-4356-abac-8782382649';
UPDATE "public"."g2p_intake_form_definitions" SET "form_description" = 'Household registration' WHERE "form_id" = '9055ab43-c85d-4833-bd00-ca657bb72650';
UPDATE "public"."g2p_registry_configuration" SET "registry_name" = 'Farmer registry' WHERE "registry_name" = 'Farmer Registry';
