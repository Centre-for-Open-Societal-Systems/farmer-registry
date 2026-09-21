-- Labels introduced by Farmer extension layout overrides. Keep this file after
-- registry_languages.sql so clean installations receive the same translations.
UPDATE "public"."registry_languages"
SET "core_translation" = jsonb_set(
    "core_translation"::jsonb,
    '{id}',
    to_jsonb('Farmer ID'::text),
    true
)::json
WHERE "language_code" = 'en';

-- "vc" (Verifiable Credential) import-mechanism label is missing from the
-- platform's own core catalog, surfacing as "MISSING_MESSAGE: vc (en)" in the
-- browser console wherever the import-mechanism options are rendered.
UPDATE "public"."registry_languages"
SET "core_translation" = jsonb_set(
    "core_translation"::jsonb,
    '{vc}',
    to_jsonb('Verifiable Credential'::text),
    true
)::json
WHERE "language_code" = 'en';

-- The platform's 1.2.x UI still calls intake submissions "Form Submissions"
-- (home card, register tab, search box); the platform has since renamed the
-- concept to "Intake Form" and the other registries show that. Same wording
-- here, so the Farmer portal reads like the rest of the suite.
--
-- With that rename the register page's "..." menu read "Intake Form" (the
-- submissions list) directly above "Intake Forms" (the submenu that starts
-- a new one). The submenu is "New Intake" -- the same words as the button on
-- the intake list page -- so the two entries say what they do.
UPDATE "public"."registry_languages"
SET "core_translation" = (
    "core_translation"::jsonb
    || jsonb_build_object(
        'form_submissions', 'Intake Form',
        'register_form_submissions', '{subject} - Intake Form',
        'register_form_submission', '{subject} - Intake Form',
        'search_form_submissions', 'Search in Intake Form',
        'intake_forms', 'New Intake'
    )
)::json
WHERE "language_code" = 'en';

-- Postgres caps function calls at 100 arguments (FUNC_MAX_ARGS), so a single
-- jsonb_build_object() holds at most 50 label pairs. This statement had grown
-- past that and was failing wholesale at seed time ("cannot pass more than
-- 100 arguments to a function"), silently dropping every label in it.
-- Concatenate multiple <=50-pair objects; add new labels to one with room.
UPDATE "public"."registry_languages"
SET "domain_translation" = (
    "domain_translation"::jsonb
    || jsonb_build_object(
        'household_income', 'Household Income',
        'state', 'State',
        'import_source', 'Import Source',
        'DRAFT', 'Draft',
        'PENDING', 'Pending',
        'APPROVED', 'Approved',
        'REJECTED', 'Rejected',
        'CANCELLED', 'Cancelled',
        'INTAKE_FORM', 'Intake Form',
        'IMPORT_FILE', 'Import File',
        'PARTNER', 'Partner',
        'STAFF_PORTAL', 'Staff Portal',
        'BENEFICIARY_PORTAL', 'Beneficiary Portal',
        'AGENT_PORTAL', 'Agent Portal',
        'VERIFIABLE_CREDENTIAL', 'Verifiable Credential',
        'farmer_ingestion_intake', 'Farmer Ingestion Intake',
        'household_ingestion_intake', 'Household Ingestion Intake',
        'birth_date', 'Date Of Birth (GC)',
        'birth_date_ec', 'Date Of Birth (EC)',
        'estimated_age', 'Age',
        'area_in_hectare', 'Area In Hectare',
        'land_kebele', 'Land Kebele Is In',
        'certificate_provided', 'Certificate Provided',
        'certificate_storage_id', 'Land Certificate',
        'land_summary', 'Land Summary',
        'total_owned_land', 'Total Owned Land',
        'total_rented_land', 'Total Rented Land',
        'total_crop_sharing_land', 'Total Crop Sharing Land',
        'total_land_area', 'Total Land Area',
        'land_ownership', 'Land Ownership',
        'is_household_head', 'Are You a Household Head?',
        'farmer_phone_numbers', 'Phone Numbers',
        'phone_type', 'Phone Type',
        'phone_number', 'Phone Number',
        'is_primary_phone', 'Primary Phone',
        'add_phone', 'Add Phone',
        'first_name_english', E'First Name\n(English)',
        'middle_name_english', E'Middle Name\n(English)',
        'last_name_english', E'Last Name\n(English)',
        'first_name_amharic', E'First Name\n(Amharic)',
        'middle_name_amharic', E'Middle Name\n(Amharic)',
        'last_name_amharic', E'Last Name\n(Amharic)',
        'first_name_afaan_oromo', E'First Name\n(Afaan Oromo)',
        'middle_name_afaan_oromo', E'Middle Name\n(Afaan Oromo)',
        'last_name_afaan_oromo', E'Last Name\n(Afaan Oromo)',
        'father_included', 'Father Included',
        'mother_included', 'Mother Included'
    )
    || jsonb_build_object(
        'number_of_males_in_family', 'Number Of Males In The Family',
        'number_of_females_in_family', 'Number Of Females In The Family',
        'number_of_children_in_family', 'Number Of Children In The Family',
        'family_size', 'Family Size',
        -- The seeded label "Other Land Owner" reads as if it asks for a
        -- person. The flag actually records whether the household farms land
        -- owned by someone outside the household (cf. the per-parcel
        -- land_ownership_type enum, which captures the same idea precisely).
        'other_land_owner', 'Household Farms Land Owned By Others',
        'farmer_photo', 'Farmer Photo',
        'names_father', E'Father''s Name',
        'father_first_name', E'Father''s First Name',
        'father_middle_name', E'Father''s Middle Name',
        'father_last_name', E'Father''s Last Name',
        -- Ethiopic twins of the Gregorian dates on the member, crop and ID
        -- tables, and the placeholder/pattern hint their text boxes show.
        'planted_date', 'Planted Date (GC)',
        'planted_date_ec', 'Planted Date (EC)',
        'expiry_date', 'Expiry Date (GC)',
        'expiry_date_ec', 'Expiry Date (EC)',
        'yyyy_mm_dd', 'YYYY-MM-DD (GC)',
        'yyyy_mm_dd_ec', 'YYYY-MM-DD (EC)',
        'certificate_file_hint', 'PDF, JPG, PNG or WebP, up to 10 MB'
    )
)::json
WHERE "language_code" = 'en';
