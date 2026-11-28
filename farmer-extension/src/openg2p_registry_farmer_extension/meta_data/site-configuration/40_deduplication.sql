-- Farmer duplicate check. Upstream matches first name, last name and birth
-- date. An Ethiopian name is the person's, the father's and the grandfather's
-- name, held in first, middle and last name, so the father's name joins the
-- match. Core scores the weighted average of
-- the fields against the register's dedup_threshold_score, which stays
-- upstream's.

UPDATE "public"."g2p_register_schemas"
SET "deduplicate_schema" = '[
  {"field_name": "first_name", "match_type": "fuzzy", "weight": 0.3},
  {"field_name": "middle_name", "match_type": "fuzzy", "weight": 0.2},
  {"field_name": "last_name", "match_type": "fuzzy", "weight": 0.2},
  {"field_name": "birth_date", "match_type": "exact", "weight": 0.3}
]'::json
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';
