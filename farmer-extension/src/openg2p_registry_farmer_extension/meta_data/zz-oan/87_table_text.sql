-- Table wording, fifth pass: the labels for the Phones, Lands, Farm inputs and
-- Livestock tables that 17_multi_choice.sql and 15_sections.sql point at. A merge
-- of named translation keys, so it is idempotent. It sorts after the other
-- translation files (and before 88_readable_text_checks.sql, which reads these labels) and wins over them; 91_table_format_checks.sql fails the
-- seed if one of these reads another way.

UPDATE "public"."registry_languages"
SET "domain_translation" = (COALESCE("domain_translation"::jsonb, '{}'::jsonb) ||
'{
 "phone_number_international": "Phone number (international)",
 "land_size_unit": "Land size unit",
 "irrigation_water_source": "Water source for irrigation",
 "farm_input_livestock_water_source": "Livestock water source (farm input)",
 "livestock_sex": "Sex",
 "phone_country_code": "Phone country (2-letter code)",
 "amount_fertilizer_utilized": "Amount of fertilizer used (kg)",
 "amount_pesticide_utilized": "Amount of pesticide used (litres)",
 "amount_insecticide_utilized": "Amount of insecticide used (litres)",
 "amount_improved_seed_utilized": "Amount of improved seed used (kg)"
}'::jsonb)::json
WHERE "language_code" = 'en';

-- phone_number_international: the phone's number with its country prefix (the
--   derived phone_e164 column), next to the number as typed.
-- land_size_unit: the unit of the land size (hectare and the like); "Unit" alone
--   is unclear in a table of many columns.
-- irrigation_water_source: the farm's irrigation water source. The crop table
--   asks the water source of each crop, so the farm-input table says irrigation.
-- farm_input_livestock_water_source: the livestock tables also ask this for each
--   animal; the "(farm input)" shows the farm-level answer is a separate one.
-- amount_*_utilized: units are an assumption (kg for fertilizer and improved
--   seed, litres for pesticide and insecticide) until the data owner confirms.
-- livestock_sex: the animal's sex; the livestock tables no longer share the
--   farmer's "gender" key.
-- phone_country_code: the 2-letter country of the phone number, not a dialling code.
