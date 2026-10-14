-- Farmer register list (SRS FR-UI-02/03, FR-06).
--
-- search_result_schema: the staff UI's table view shows Name and Farmer ID and
-- then the display fields in `order`. The stock 1.2.1 bundle stops at six; the
-- staff-ui stage of the root Dockerfile raises that to ten, so the first ten
-- below are the table columns and the card view shows all of them. Column
-- headers come from the translation catalog keyed by field_name (display_label
-- is not read by the table), see zz_farmer_translation_overrides.sql.
-- record_name_local is a read-only hybrid property on the Farmer model
-- (Amharic name, falling back to Afaan Oromo).
--
-- The staff search endpoint reads only fields on the register row, so the
-- service/migration layer keeps the geo/workflow projections aligned.
UPDATE public.g2p_register_schemas
SET search_result_schema = '[
  {"field_name":"record_name_local","display_label":"Name (Local)","order":1},
  {"field_name":"gender","display_label":"Gender","order":2},
  {"field_name":"estimated_age","display_label":"Age","order":3},
  {"field_name":"kebele_name","display_label":"Kebele","order":4},
  {"field_name":"woreda_name","display_label":"Woreda","order":5},
  {"field_name":"region_name","display_label":"Region","order":6},
  {"field_name":"created_at","display_label":"Registration Date","order":7},
  {"field_name":"state","display_label":"State","order":8},
  {"field_name":"is_duplicated","display_label":"Duplicate","order":9},
  {"field_name":"zone_name","display_label":"Zone","order":10},
  {"field_name":"import_source","display_label":"Import Source","order":11}
]'::json,
-- Region is a static dropdown of the Ethiopia hierarchy's region display names
-- (docker/local-dev/geo-seed, the same pack far's Master Data holds), because
-- filter options cannot be sourced from Master Data. Woreda is a text match:
-- a dropdown dependent on Region needs a filter type the platform lacks.
-- Gender and Birthdate were in the base layer (g2p_register_schemas.sql) and
-- had been dropped by this override.
filter_schema = '[
  {"field_name":"first_name","display_label":"First Name","filter_type":"text","order":1,"allowed_operators":["eq","contains"]},
  {"field_name":"last_name","display_label":"Last Name","filter_type":"text","order":2,"allowed_operators":["eq","contains"]},
  {"field_name":"region_name","display_label":"Region","filter_type":"dropdown","order":3,"allowed_operators":["eq","in"],"options_source":[{"value":"Addis Ababa","label":"Addis Ababa"},{"value":"Afar","label":"Afar"},{"value":"Amhara","label":"Amhara"},{"value":"Benishangul-Gumuz","label":"Benishangul-Gumuz"},{"value":"Central Ethiopia","label":"Central Ethiopia"},{"value":"Dire Dawa","label":"Dire Dawa"},{"value":"Gambela","label":"Gambela"},{"value":"Harari","label":"Harari"},{"value":"Oromia","label":"Oromia"},{"value":"Sidama","label":"Sidama"},{"value":"Somali","label":"Somali"},{"value":"South Ethiopian","label":"South Ethiopian"},{"value":"South West Ethiopia","label":"South West Ethiopia"},{"value":"Tigray","label":"Tigray"}]},
  {"field_name":"woreda_name","display_label":"Woreda","filter_type":"text","order":4,"allowed_operators":["eq","contains"]},
  {"field_name":"gender","display_label":"Gender","filter_type":"dropdown","order":5,"allowed_operators":["eq","in"],"options_source":[{"value":"MALE","label":"MALE"},{"value":"FEMALE","label":"FEMALE"},{"value":"OTHERS","label":"OTHERS"},{"value":"UNKNOWN","label":"UNKNOWN"}]},
  {"field_name":"birth_date","display_label":"Birthdate","filter_type":"date_range","order":6,"allowed_operators":["eq","gt","gte","lt","lte","between"]},
  {"field_name":"state","display_label":"State","filter_type":"dropdown","order":7,"allowed_operators":["eq","in"],"options_source":[{"value":"DRAFT","label":"Draft"},{"value":"PENDING","label":"Pending"},{"value":"APPROVED","label":"Approved"},{"value":"REJECTED","label":"Rejected"},{"value":"CANCELLED","label":"Cancelled"}]},
  {"field_name":"import_source","display_label":"Import Source","filter_type":"dropdown","order":8,"allowed_operators":["eq","in"],"options_source":[{"value":"INTAKE_FORM","label":"Intake Form"},{"value":"IMPORT_FILE","label":"Import File"},{"value":"PARTNER","label":"Partner"},{"value":"STAFF_PORTAL","label":"Staff Portal"},{"value":"BENEFICIARY_PORTAL","label":"Beneficiary Portal"},{"value":"AGENT_PORTAL","label":"Agent Portal"},{"value":"VERIFIABLE_CREDENTIAL","label":"Verifiable Credential"}]},
  {"field_name":"record_status","display_label":"Record Status","filter_type":"dropdown","order":9,"allowed_operators":["eq","in"],"options_source":[{"value":"ACTIVE","label":"Active"},{"value":"INACTIVE","label":"Inactive"},{"value":"ARCHIVED","label":"Archived"}]},
  {"field_name":"is_duplicated","display_label":"Duplicate Status","filter_type":"dropdown","order":10,"allowed_operators":["eq","in"],"options_source":[{"value":"true","label":"DUPLICATE"},{"value":"false","label":"UNIQUE"}]}
]'::json
WHERE register_id = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';
