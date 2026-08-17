-- Farmer list cards expose workflow provenance as flattened Farmer fields.
-- The staff search endpoint reads only fields on the register row, so the
-- service/migration layer keeps these projections aligned with workflow data.
UPDATE public.g2p_register_schemas
SET search_result_schema = '[
  {"field_name":"region_name","display_label":"Region","order":1},
  {"field_name":"zone_name","display_label":"Zone","order":2},
  {"field_name":"woreda_name","display_label":"Woreda","order":3},
  {"field_name":"kebele_name","display_label":"Kebele","order":4},
  {"field_name":"state","display_label":"State","order":5},
  {"field_name":"import_source","display_label":"Import Source","order":6}
]'::json,
filter_schema = '[
  {"field_name":"first_name","display_label":"First Name","filter_type":"text","order":1,"allowed_operators":["eq","contains"]},
  {"field_name":"last_name","display_label":"Last Name","filter_type":"text","order":2,"allowed_operators":["eq","contains"]},
  {"field_name":"state","display_label":"State","filter_type":"dropdown","order":3,"allowed_operators":["eq","in"],"options_source":[{"value":"DRAFT","label":"Draft"},{"value":"PENDING","label":"Pending"},{"value":"APPROVED","label":"Approved"},{"value":"REJECTED","label":"Rejected"},{"value":"CANCELLED","label":"Cancelled"}]},
  {"field_name":"import_source","display_label":"Import Source","filter_type":"dropdown","order":4,"allowed_operators":["eq","in"],"options_source":[{"value":"INTAKE_FORM","label":"Intake Form"},{"value":"IMPORT_FILE","label":"Import File"},{"value":"PARTNER","label":"Partner"},{"value":"STAFF_PORTAL","label":"Staff Portal"},{"value":"BENEFICIARY_PORTAL","label":"Beneficiary Portal"},{"value":"AGENT_PORTAL","label":"Agent Portal"},{"value":"VERIFIABLE_CREDENTIAL","label":"Verifiable Credential"}]},
  {"field_name":"record_status","display_label":"Record Status","filter_type":"dropdown","order":5,"allowed_operators":["eq","in"],"options_source":[{"value":"ACTIVE","label":"Active"},{"value":"INACTIVE","label":"Inactive"},{"value":"ARCHIVED","label":"Archived"}]}
]'::json
WHERE register_id = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';
