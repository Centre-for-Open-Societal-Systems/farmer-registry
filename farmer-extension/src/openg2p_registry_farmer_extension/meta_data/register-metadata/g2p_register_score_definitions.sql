INSERT INTO "public"."g2p_register_score_definitions" (
    "score_definition_id",
    "register_mnemonic",
    "score_type",
    "is_enabled"
) VALUES (
    'e7269b21-f234-411a-bb4d-16ca8b5f3cd3',
    'Household',
    'POVERTY',
    'TRUE'
)

-- Upsert, not a bare INSERT: on an existing database a bare INSERT hits the
-- primary key and the WHOLE statement fails (db-seed runs with
-- ON_ERROR_STOP=0, so silently), and no row added or changed in this file
-- after the first seed ever reached that environment. The zz_*.sql files
-- still run after this and still win.
ON CONFLICT ("score_definition_id") DO UPDATE SET
    "register_mnemonic" = EXCLUDED."register_mnemonic",
    "score_type" = EXCLUDED."score_type",
    "is_enabled" = EXCLUDED."is_enabled";
