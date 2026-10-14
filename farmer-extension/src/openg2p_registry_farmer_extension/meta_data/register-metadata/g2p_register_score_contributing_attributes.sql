INSERT INTO "public"."g2p_register_score_contributing_attributes" (
    "contributing_attribute_id",
    "register_mnemonic",
    "score_type",
    "attribute_name",
    "attribute_computation_required",
    "attribute_computation_value",
    "attribute_weightage"
) VALUES
(
    'ca7269b2-f234-411a-bb4d-16ca8b5f3cd1',
    'Household',
    'POVERTY',
    'size_of_group',
    'FALSE',
    NULL,
    0.45
),
(
    'ca7269b2-f234-411a-bb4d-16ca8b5f3cd2',
    'Household',
    'POVERTY',
    'number_of_children',
    'FALSE',
    NULL,
    0.55
)

-- Upsert, not a bare INSERT: on an existing database a bare INSERT hits the
-- primary key and the WHOLE statement fails (db-seed runs with
-- ON_ERROR_STOP=0, so silently), and no row added or changed in this file
-- after the first seed ever reached that environment. The zz_*.sql files
-- still run after this and still win.
ON CONFLICT ("contributing_attribute_id") DO UPDATE SET
    "register_mnemonic" = EXCLUDED."register_mnemonic",
    "score_type" = EXCLUDED."score_type",
    "attribute_name" = EXCLUDED."attribute_name",
    "attribute_computation_required" = EXCLUDED."attribute_computation_required",
    "attribute_computation_value" = EXCLUDED."attribute_computation_value",
    "attribute_weightage" = EXCLUDED."attribute_weightage";
