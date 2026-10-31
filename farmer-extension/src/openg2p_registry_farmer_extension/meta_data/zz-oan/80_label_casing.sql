-- Label casing: sentence case for everything staff read that OAN metadata defines.
-- Labels, section and tab titles, table headings, messages and dropdown filter
-- labels use sentence case; acronyms and proper nouns (ID, FAN, FIN, Fayda,
-- Kebele, Woreda, ODK, DA) keep their case, and raw codes are not shown as
-- labels. Only display text changes: translation keys, ids, codes and
-- mnemonics are untouched.
--
-- Every statement is an explicit-id UPDATE (or a merge of named translation
-- keys), so it is idempotent and a plain upgrade applies it to databases that
-- already hold the older text. It sorts after the older seed files of this
-- package, so it also wins on a fresh install.

-- Display labels: domain translations (English)
UPDATE "public"."registry_languages"
SET "domain_translation" = (COALESCE("domain_translation"::jsonb, '{}'::jsonb) ||
'{
 "aadhaar_card": "Aadhaar card",
 "access_to_finance": "Access to finance",
 "access_to_machinery": "Access to machinery",
 "add_crop": "Add crop",
 "add_farm": "Add farm",
 "add_farm_input": "Add farm input",
 "add_livestock_record": "Add livestock record",
 "add_member": "Add member",
 "address_line_1": "Address line 1",
 "address_line_2": "Address line 2",
 "A_LOT_OF_DIFFICULTY": "A lot of difficulty",
 "amount_fertilizer_utilized": "Fertilizer used",
 "amount_improved_seed_utilized": "Improved seed used",
 "amount_insecticide_utilized": "Insecticide used",
 "amount_pesticide_utilized": "Pesticide used",
 "bank_document": "Bank account evidence",
 "bank_document_type": "Bank document type",
 "bank_passbook": "Bank passbook",
 "BIOFUELS_NONFOOD": "Biofuels (non-food)",
 "birth_date": "Birth date",
 "birth_date_ec": "Birth date (Ethiopian)",
 "body_condition": "Body condition",
 "CANNOT_DO_AT_ALL": "Cannot do at all",
 "CAN_READ_AND_WRITE": "Can read and write",
 "certificate_storage_id": "Certificate storage ID",
 "click_to_search_household": "Click to search household",
 "collected_date": "Count date",
 "computation_scores": "Computation scores",
 "cooperative_union": "Cooperative union",
 "cooperative_union_name": "Cooperative union name",
 "country_code": "Country code",
 "CROP_PRODUCTION": "Crop production",
 "CROP_SHARE": "Crop share",
 "current_land_use": "Current land use",
 "data_collection_date": "Data collection date",
 "disability_severity": "Disability severity",
 "disability_type": "Disability type",
 "disease_type": "Disease or pest",
 "DIVORCE_SETTLEMENT": "Divorce settlement",
 "DONATION_GIFT": "Donation / gift",
 "education_level": "Education level",
 "end_use": "End use",
 "enter_address_line_1": "Enter address line 1",
 "enter_address_line_2": "Enter address line 2",
 "enter_altitude": "Enter altitude",
 "enter_latitude": "Enter latitude",
 "enter_longitude": "Enter longitude",
 "enumerator_accuracy": "Enumerator accuracy (m)",
 "enumerator_altitude": "Enumerator altitude (m)",
 "enumerator_latitude": "Enumerator latitude",
 "enumerator_longitude": "Enumerator longitude",
 "enumerator_name": "Enumerator name",
 "enumerator_user_id": "Enumerator user ID",
 "estimated_age": "Estimated age",
 "farmer_certificate": "Farmer certificate",
 "farmer_cluster": "Farmer cluster",
 "farmer_cluster_role": "Farmer cluster role",
 "farmer_document": "Farmer / cooperative evidence",
 "farmer_document_type": "Farmer / cooperative document type",
 "farmer_farm_inputs": "Farm inputs",
 "farmer_farm_inputs_tab": "Farm inputs",
 "farmer_household_information": "Household information",
 "farmer_household_location": "Household location",
 "farmer_household_members": "Household members",
 "farmer_ingestion_intake": "Farmer ingestion intake",
 "farmer_intake": "Farmer intake",
 "farmer_intake_tab": "Farmer intake",
 "farmer_location": "Farmer location",
 "farmer_memberships": "Membership details",
 "farmer_memberships_tab": "Membership details",
 "farmer_personal_details": "Personal details",
 "farmer_personal_information": "Personal information",
 "farmer_photo": "Farmer photo",
 "farmers_language": "Farmer''s language",
 "farmer_socio_economic_and_health": "Socio-economic & health",
 "farming_type": "Farming type",
 "farm_inputs": "Farm inputs",
 "FarmInputs": "Farm inputs",
 "father_included": "Father included",
 "fathers_name_eng": "Father''s name (English)",
 "fathers_name_local": "Father''s name (farmer''s language)",
 "FEED_ANIMALS": "Feed animals",
 "fertilizer_use": "Fertilizer use",
 "first_name_eng": "First name (English)",
 "first_name": "First name",
 "first_name_local": "First name (farmer''s language)",
 "FOOD_HUMAN_CONSUMPTION": "Food (human consumption)",
 "fr_farmer_farm_input": "Farm inputs",
 "fr_farmer_membership": "Membership details",
 "fr_farmer_personal_info": "Personal information",
 "fr_farmer_socio_and_health": "Socio-economic & health",
 "fr_household_information": "Household information",
 "fr_household_location": "Household location",
 "fr_household_members": "Household members",
 "GOVERNMENT_NGO_SUPPORT": "Government / NGO support",
 "grandfathers_name_eng": "Grandfather''s name (English)",
 "grandfathers_name_local": "Grandfather''s name (farmer''s language)",
 "has_national_id": "Has national ID",
 "head_count": "Head count",
 "health_details": "Health details",
 "hh_farmer_location": "Farmer location",
 "hh_farmer_personal_info": "Farmer personal information",
 "hh_farmer_socio_and_health": "Farmer socio-economic & health",
 "hh_household_farmer_location": "Farmer location",
 "hh_household_information": "Household information",
 "hh_household_members": "Household members",
 "hh_information": "Household information",
 "hh_location": "Household location",
 "hh_members": "Household members",
 "HIGHER_EDUCATION": "Higher education",
 "household_computation_scores": "Computation scores",
 "household_farmer_location_details": "Location details",
 "household_farmer_location": "Farmer location",
 "household_farmer_personal_information": "Farmer personal information",
 "household_head": "Household head",
 "household_household_information": "Household information",
 "household_information": "Household information",
 "household_ingestion_intake": "Household ingestion intake",
 "household_intake_tab": "Household intake",
 "household_location": "Household location",
 "household_lookup_helptext": "Pick the household if it is already registered. For a new household, leave this empty and fill in household information and household members below.",
 "HouseholdMember": "Household members",
 "household_members": "Household members",
 "household_members_records": "Household members records",
 "household_socio_economic_and_health": "Farmer socio-economic & health",
 "identity_document": "Identity document",
 "identity_document_type": "Identity document type",
 "id_proof": "ID proof",
 "improved_seed_use": "Improved seed use",
 "insecticide_use": "Insecticide use",
 "intake_fr_farmer_farm_input": "Farm inputs",
 "IRRIGATION_GROUND_WATER": "Ground water irrigation",
 "IRRIGATION_SURFACE_WATER": "Surface water irrigation",
 "irrigation_type": "Irrigation type",
 "is_cooperative_union_member": "Is cooperative union member",
 "is_farmer_cluster_member": "Is farmer cluster member",
 "is_farmer": "Is a farmer",
 "is_head": "Is head",
 "is_household_head": "Household head",
 "is_primary_cooperative_member": "Is primary cooperative member",
 "is_psnp_user": "PSNP beneficiary",
 "land_certificate": "Land certificate",
 "land_document": "Landholding / land-use document",
 "land_document_type": "Land document type",
 "land_ownership": "Land ownership",
 "land_ownership_type": "Land ownership type",
 "land_size": "Land size",
 "land_summary": "Land summary",
 "last_name": "Last name",
 "LIVESTOCK_PRODUCTION": "Livestock production",
 "livestock_system": "Livestock system",
 "livestock_type": "Livestock type",
 "livestock_water_source": "Livestock water source",
 "location_details": "Location details",
 "machinery_type": "Machinery used",
 "marital_status": "Marital status",
 "means_of_acquisition": "Means of acquisition",
 "MembershipDetails": "Membership details",
 "middle_name": "Middle name",
 "mother_included": "Mother included",
 "NO_DIFFICULTY": "No difficulty",
 "NOMADIC_PASTORAL": "Nomadic pastoral",
 "number_of_children": "Number of children",
 "number_of_elderly_members": "Number of elderly members",
 "number_of_female_members": "Number of female members",
 "number_of_male_members": "Number of male members",
 "num_female_members": "Number of female members",
 "num_male_members": "Number of male members",
 "odk_farmer_id": "ODK farmer ID",
 "other_document_name": "Document name",
 "other_document": "Other supporting document",
 "other_farmer_in_household": "Another farmer in the household",
 "other_land_owner": "Other land owner",
 "OTHER_RELATIVE": "Other relative",
 "pan_card": "PAN card",
 "personal_information": "Personal information",
 "pesticide_use": "Pesticide use",
 "phone_number": "Phone number",
 "phone_numbers": "Phone numbers",
 "phone_type": "Phone type",
 "planted_date": "Planted date",
 "postal_code": "Postal code",
 "primary_commodity": "Primary commodity",
 "primary_cooperative_name": "Primary cooperative name",
 "primary_cooperative": "Primary cooperative",
 "production_type": "Production type",
 "record_name": "Record name",
 "register_fr_farmer_farm_input": "Farm inputs",
 "relationship_to_the_head_helptext": "Leave empty for the head (saved as self); required for every other member",
 "relationship_to_the_head": "Relationship to the head",
 "RENTING_LEASING": "Renting / leasing",
 "representative_document": "Representative / guardian document",
 "representative_document_type": "Representative document type",
 "required_household_fields": "Size of group, male/female counts and other land owner are required",
 "search_by_name_or_id": "Search by name or ID",
 "SEDENTARY_PASTORAL": "Sedentary pastoral",
 "select_household": "Select household",
 "SELF_CARE": "Self care",
 "SELF": "Self (head)",
 "SEMI_NOMADIC": "Semi nomadic",
 "size_of_group": "Size of group",
 "socio_economic_and_health": "Socio-economic & health details",
 "socio_economic_details": "Socio economic details",
 "SOI_CROP_PRODUCTION": "Crop production",
 "SOI_GOVERNMENT_NGO_SUPPORT": "Government / NGO support",
 "soil_fertility": "Soil fertility",
 "SOI_LIVESTOCK_PRODUCTION": "Livestock production",
 "SOME_DIFFICULTY": "Some difficulty",
 "source_of_income_other": "Other source of income",
 "source_of_income": "Source of income",
 "SQUARE_FOOT": "Square foot",
 "SQUARE_KM": "Square km",
 "SQUARE_METER": "Square meter",
 "SQUARE_YARD": "Square yard",
 "sub_region": "Sub region",
 "SURFACE_WATER": "Surface water",
 "total_land_area": "Total land area (ha)",
 "total_land_crop_sharing_area": "Crop-sharing land (ha)",
 "total_land_owned_area": "Owned land (ha)",
 "total_land_rent_area": "Rented land (ha)",
 "WATER_HARVESTING": "Water harvesting",
 "water_source": "Water source",
 "WELL_GROUND_WATER": "Well ground water",
 "year_of_acquisition": "Year of acquisition"
}'::jsonb)::json
WHERE "language_code" = 'en';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"select_record_label": "Select Parent"', '"select_record_label": "Select parent"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_farm_inputs_intake';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"select_record_label": "Select Parent"', '"select_record_label": "Select parent"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_livestock_intake';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(replace(replace(replace(replace(replace(replace(section_ui_schema::text, '"widget-label": "Location Hierarchy"', '"widget-label": "Location hierarchy"'), '"widget-label": "Address Line 1"', '"widget-label": "Address line 1"'), '"widget-label": "Address Line 2"', '"widget-label": "Address line 2"'), '"widget-label": "Postal Code"', '"widget-label": "Postal code"'), '"widget-label": "Country Code"', '"widget-label": "Country code"'), '"widget-label": "Plus Code"', '"widget-label": "Plus code"'), '"patternMessage": "Enter a valid Plus Code (for example 35AB+14 or 8FVC9G8F+6W)"', '"patternMessage": "Enter a valid plus code (for example 35AB+14 or 8FVC9G8F+6W)"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_location';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"select_record_label": "Select Parent"', '"select_record_label": "Select parent"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_livestock';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"select_record_label": "Select Parent"', '"select_record_label": "Select parent"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_crop_crop_details_section_01';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(replace(replace(replace(replace(replace(replace(section_ui_schema::text, '"widget-label": "Location Hierarchy"', '"widget-label": "Location hierarchy"'), '"widget-label": "Address Line 1"', '"widget-label": "Address line 1"'), '"widget-label": "Address Line 2"', '"widget-label": "Address line 2"'), '"widget-label": "Postal Code"', '"widget-label": "Postal code"'), '"widget-label": "Country Code"', '"widget-label": "Country code"'), '"widget-label": "Plus Code"', '"widget-label": "Plus code"'), '"patternMessage": "Enter a valid Plus Code (for example 35AB+14 or 8FVC9G8F+6W)"', '"patternMessage": "Enter a valid plus code (for example 35AB+14 or 8FVC9G8F+6W)"')::jsonb
WHERE "register_id" = '9055ab43-c85d-4833-bd00-ca657bb72644' AND "section_id" = 'household_farmer_location_section_03';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"select_record_label": "Select Parent"', '"select_record_label": "Select parent"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_livestock_livestock_details_intake_section_01';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(replace(replace(replace(replace(replace(replace(section_ui_schema::text, '"widget-label": "Location Hierarchy"', '"widget-label": "Location hierarchy"'), '"widget-label": "Address Line 1"', '"widget-label": "Address line 1"'), '"widget-label": "Address Line 2"', '"widget-label": "Address line 2"'), '"widget-label": "Postal Code"', '"widget-label": "Postal code"'), '"widget-label": "Country Code"', '"widget-label": "Country code"'), '"widget-label": "Plus Code"', '"widget-label": "Plus code"'), '"patternMessage": "Enter a valid Plus Code (for example 35AB+14 or 8FVC9G8F+6W)"', '"patternMessage": "Enter a valid plus code (for example 35AB+14 or 8FVC9G8F+6W)"')::jsonb
WHERE "register_id" = '9055ab43-c85d-4833-bd00-ca657bb72644' AND "section_id" = 'household_household_location_section_03';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"select_record_label": "Select Parent"', '"select_record_label": "Select parent"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_farm_inputs';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(replace(replace(replace(replace(replace(replace(section_ui_schema::text, '"widget-label": "Location Hierarchy"', '"widget-label": "Location hierarchy"'), '"widget-label": "Address Line 1"', '"widget-label": "Address line 1"'), '"widget-label": "Address Line 2"', '"widget-label": "Address line 2"'), '"widget-label": "Postal Code"', '"widget-label": "Postal code"'), '"widget-label": "Country Code"', '"widget-label": "Country code"'), '"widget-label": "Plus Code"', '"widget-label": "Plus code"'), '"patternMessage": "Enter a valid Plus Code (for example 35AB+14 or 8FVC9G8F+6W)"', '"patternMessage": "Enter a valid plus code (for example 35AB+14 or 8FVC9G8F+6W)"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_household_location_section_03';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(replace(replace(replace(replace(replace(replace(section_ui_schema::text, '"widget-label": "Location Hierarchy"', '"widget-label": "Location hierarchy"'), '"widget-label": "Address Line 1"', '"widget-label": "Address line 1"'), '"widget-label": "Address Line 2"', '"widget-label": "Address line 2"'), '"widget-label": "Postal Code"', '"widget-label": "Postal code"'), '"widget-label": "Country Code"', '"widget-label": "Country code"'), '"widget-label": "Plus Code"', '"widget-label": "Plus code"'), '"patternMessage": "Enter a valid Plus Code (for example 35AB+14 or 8FVC9G8F+6W)"', '"patternMessage": "Enter a valid plus code (for example 35AB+14 or 8FVC9G8F+6W)"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_farmer_location_section_03';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"select_record_label": "Select Parent"', '"select_record_label": "Select parent"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_crops_intake';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"select_record_label": "Select Parent"', '"select_record_label": "Select parent"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_farm_input_farm_input_details_intake_section_01';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"select_record_label": "Select Parent"', '"select_record_label": "Select parent"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_crops';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"select_record_label": "Select Parent"', '"select_record_label": "Select parent"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_crop_crop_details_intake_section_01';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"select_record_label": "Select Parent"', '"select_record_label": "Select parent"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_farm_input_farm_input_details_section_01';

UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = replace(section_ui_schema::text, '"select_record_label": "Select Parent"', '"select_record_label": "Select parent"')::jsonb
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd' AND "section_id" = 'farmer_livestock_livestock_details_section_01';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace(replace("search_result_schema"::jsonb::text, '"display_label": "End Use"', '"display_label": "End use"'), '"display_label": "Planted Date"', '"display_label": "Planted date"')::json
WHERE "register_id" = '5fa096f8-ffdc-4b0a-ab16-9ca386c23310';

UPDATE "public"."g2p_register_schemas"
SET "filter_schema" = replace("filter_schema"::jsonb::text, '"display_label": "End Use"', '"display_label": "End use"')::json
WHERE "register_id" = '5fa096f8-ffdc-4b0a-ab16-9ca386c23310';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace(replace("search_result_schema"::jsonb::text, '"display_label": "Phone Type"', '"display_label": "Phone type"'), '"display_label": "Phone Number"', '"display_label": "Phone number"')::json
WHERE "register_id" = 'c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f';

UPDATE "public"."g2p_register_schemas"
SET "filter_schema" = replace("filter_schema"::jsonb::text, '"display_label": "Phone Number"', '"display_label": "Phone number"')::json
WHERE "register_id" = 'c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace(replace(replace(replace(replace("search_result_schema"::jsonb::text, '"display_label": "Farm Input ID"', '"display_label": "Farm input ID"'), '"display_label": "Fertilizer Use"', '"display_label": "Fertilizer use"'), '"display_label": "Pesticide Use"', '"display_label": "Pesticide use"'), '"display_label": "Improved Seed Use"', '"display_label": "Improved seed use"'), '"display_label": "Water Source"', '"display_label": "Water source"')::json
WHERE "register_id" = '18df8370-3e9a-493f-aa27-fc1b9e05629c';

UPDATE "public"."g2p_register_schemas"
SET "filter_schema" = replace(replace(replace("filter_schema"::jsonb::text, '"display_label": "Fertilizer Use"', '"display_label": "Fertilizer use"'), '"display_label": "Pesticide Use"', '"display_label": "Pesticide use"'), '"display_label": "Water Source"', '"display_label": "Water source"')::json
WHERE "register_id" = '18df8370-3e9a-493f-aa27-fc1b9e05629c';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace(replace(replace("search_result_schema"::jsonb::text, '"display_label": "Livestock Type"', '"display_label": "Livestock type"'), '"display_label": "Head Count"', '"display_label": "Head count"'), '"display_label": "Livestock System"', '"display_label": "Livestock system"')::json
WHERE "register_id" = '4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb';

UPDATE "public"."g2p_register_schemas"
SET "filter_schema" = replace(replace(replace("filter_schema"::jsonb::text, '"display_label": "Livestock Type"', '"display_label": "Livestock type"'), '"display_label": "Head Count"', '"display_label": "Head count"'), '"display_label": "Livestock System"', '"display_label": "Livestock system"')::json
WHERE "register_id" = '4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace(replace(replace(replace("search_result_schema"::jsonb::text, '"display_label": "Primary Cooperative Member"', '"display_label": "Primary cooperative member"'), '"display_label": "Primary Cooperative Name"', '"display_label": "Primary cooperative name"'), '"display_label": "Farmer Cluster Member"', '"display_label": "Farmer cluster member"'), '"display_label": "Cluster Role"', '"display_label": "Cluster role"')::json
WHERE "register_id" = '495f251c-83a5-4025-a307-1925712c9d0b';

UPDATE "public"."g2p_register_schemas"
SET "filter_schema" = replace(replace(replace("filter_schema"::jsonb::text, '"display_label": "Primary Cooperative Member"', '"display_label": "Primary cooperative member"'), '"display_label": "Cooperative Union Member"', '"display_label": "Cooperative union member"'), '"display_label": "Cluster Role"', '"display_label": "Cluster role"')::json
WHERE "register_id" = '495f251c-83a5-4025-a307-1925712c9d0b';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace(replace(replace("search_result_schema"::jsonb::text, '"display_label": "Poverty Score ID"', '"display_label": "Poverty score ID"'), '"display_label": "Poverty Score"', '"display_label": "Poverty score"'), '"display_label": "Score Type"', '"display_label": "Score type"')::json
WHERE "register_id" = '37b44544-4203-4215-ab1e-944994f425ea';

UPDATE "public"."g2p_register_schemas"
SET "filter_schema" = replace(replace("filter_schema"::jsonb::text, '"display_label": "Poverty Score"', '"display_label": "Poverty score"'), '"display_label": "Score Type"', '"display_label": "Score type"')::json
WHERE "register_id" = '37b44544-4203-4215-ab1e-944994f425ea';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace(replace(replace(replace("search_result_schema"::jsonb::text, '"display_label": "Size of Group"', '"display_label": "Size of group"'), '"display_label": "Number of Male Members"', '"display_label": "Number of male members"'), '"display_label": "Number of Female Members"', '"display_label": "Number of female members"'), '"display_label": "Number Of Elderly Members"', '"display_label": "Number of elderly members"')::json
WHERE "register_id" = '9055ab43-c85d-4833-bd00-ca657bb72644';

UPDATE "public"."g2p_register_schemas"
SET "filter_schema" = replace(replace(replace(replace(replace(replace(replace(replace("filter_schema"::jsonb::text, '"display_label": "Size of Group"', '"display_label": "Size of group"'), '"display_label": "Number of Male Members"', '"display_label": "Number of male members"'), '"display_label": "Number of Female Members"', '"display_label": "Number of female members"'), '"display_label": "Number Of Elderly Members"', '"display_label": "Number of elderly members"'), '"display_label": "Record Status"', '"display_label": "Record status"'), '"label": "ACTIVE"', '"label": "Active"'), '"label": "INACTIVE"', '"label": "Inactive"'), '"label": "ARCHIVED"', '"label": "Archived"')::json
WHERE "register_id" = '9055ab43-c85d-4833-bd00-ca657bb72644';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace(replace(replace(replace(replace("search_result_schema"::jsonb::text, '"display_label": "First Name"', '"display_label": "First name"'), '"display_label": "Last Name"', '"display_label": "Last name"'), '"display_label": "Is Head"', '"display_label": "Is head"'), '"display_label": "Relationship To The Head"', '"display_label": "Relationship to the head"'), '"display_label": "Is Disabled"', '"display_label": "Is disabled"')::json
WHERE "register_id" = '52979fdd-220c-48dd-8de0-0a434e786427';

UPDATE "public"."g2p_register_schemas"
SET "filter_schema" = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace("filter_schema"::jsonb::text, '"display_label": "First Name"', '"display_label": "First name"'), '"display_label": "Last Name"', '"display_label": "Last name"'), '"display_label": "Is Head"', '"display_label": "Is head"'), '"display_label": "Relationship To The Head"', '"display_label": "Relationship to the head"'), '"label": "SELF"', '"label": "Self"'), '"label": "SPOUSE"', '"label": "Spouse"'), '"label": "CHILD"', '"label": "Child"'), '"label": "PARENT"', '"label": "Parent"'), '"label": "SIBLING"', '"label": "Sibling"'), '"label": "OTHER_RELATIVE"', '"label": "Other relative"'), '"label": "NON_RELATIVE"', '"label": "Non relative"'), '"display_label": "Is Disabled"', '"display_label": "Is disabled"')::json
WHERE "register_id" = '52979fdd-220c-48dd-8de0-0a434e786427';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace(replace("search_result_schema"::jsonb::text, '"display_label": "Ownership Type"', '"display_label": "Ownership type"'), '"display_label": "Land Size"', '"display_label": "Land size"')::json
WHERE "register_id" = '493153d5-07ef-4743-8efd-07f4099772b9';

UPDATE "public"."g2p_register_schemas"
SET "filter_schema" = replace("filter_schema"::jsonb::text, '"display_label": "Ownership Type"', '"display_label": "Ownership type"')::json
WHERE "register_id" = '493153d5-07ef-4743-8efd-07f4099772b9';

UPDATE "public"."g2p_register_schemas"
SET "search_result_schema" = replace(replace(replace(replace(replace("search_result_schema"::jsonb::text, '"display_label": "Education Level"', '"display_label": "Education level"'), '"display_label": "First Name"', '"display_label": "First name"'), '"display_label": "Last Name"', '"display_label": "Last name"'), '"display_label": "Birth Date"', '"display_label": "Birth date"'), '"display_label": "Marital Status"', '"display_label": "Marital status"')::json
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';

UPDATE "public"."g2p_register_schemas"
SET "filter_schema" = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace("filter_schema"::jsonb::text, '"display_label": "First Name"', '"display_label": "First name"'), '"display_label": "Last Name"', '"display_label": "Last name"'), '"label": "MALE"', '"label": "Male"'), '"label": "FEMALE"', '"label": "Female"'), '"label": "OTHERS"', '"label": "Others"'), '"label": "UNKNOWN"', '"label": "Unknown"'), '"display_label": "Record Status"', '"display_label": "Record status"'), '"label": "ACTIVE"', '"label": "Active"'), '"label": "INACTIVE"', '"label": "Inactive"'), '"label": "ARCHIVED"', '"label": "Archived"')::json
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';

UPDATE "public"."g2p_register_definitions"
SET "register_subject" = 'Household members'
WHERE "register_id" = '52979fdd-220c-48dd-8de0-0a434e786427';

UPDATE "public"."g2p_register_definitions"
SET "register_subject" = 'Farmer phones'
WHERE "register_id" = 'c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f';

UPDATE "public"."g2p_register_definitions"
SET "register_subject" = 'Farm inputs'
WHERE "register_id" = '18df8370-3e9a-493f-aa27-fc1b9e05629c';

UPDATE "public"."g2p_register_definitions"
SET "register_subject" = 'Membership details'
WHERE "register_id" = '495f251c-83a5-4025-a307-1925712c9d0b';

UPDATE "public"."g2p_intake_form_definitions"
SET "form_description" = 'Farmer ingestion intake'
WHERE "form_id" = 'a1a4d25a-1cd4-4356-abac-8782382649';

UPDATE "public"."g2p_intake_form_definitions"
SET "form_description" = 'Household ingestion intake'
WHERE "form_id" = '9055ab43-c85d-4833-bd00-ca657bb72650';
