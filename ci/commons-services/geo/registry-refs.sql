-- Every location id the registry references anywhere: the id columns, the ids
-- inside geo_code_hierarchy_json, and both inside change-request snapshots.
-- One id per line. Read-only in effect; the caller wraps it in BEGIN .. ROLLBACK
-- because the temp table needs a write transaction.
CREATE TEMP TABLE _r (id varchar PRIMARY KEY) ON COMMIT DROP;
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT c.table_name, c.column_name, c.data_type
               FROM information_schema.columns c
               JOIN information_schema.tables t
                 ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                AND t.table_type = 'BASE TABLE'
              WHERE c.table_schema = 'public'
                AND c.column_name IN ('geo_lowest_level_value_id', 'woreda_level_value_id',
                                      'geo_code_hierarchy_json')
    LOOP
        IF r.column_name = 'geo_code_hierarchy_json' THEN
            EXECUTE format('INSERT INTO _r SELECT DISTINCT h ->> ''level_value_id'' FROM %I x,'
                           ' jsonb_array_elements(CASE WHEN jsonb_typeof(x.%I::jsonb -> ''hierarchy'') = ''array'''
                           '   THEN x.%I::jsonb -> ''hierarchy'' ELSE ''[]''::jsonb END) h'
                           ' WHERE h ->> ''level_value_id'' IS NOT NULL ON CONFLICT DO NOTHING',
                           r.table_name, r.column_name, r.column_name);
        ELSE
            EXECUTE format('INSERT INTO _r SELECT DISTINCT %I FROM %I WHERE %I IS NOT NULL ON CONFLICT DO NOTHING',
                           r.column_name, r.table_name, r.column_name);
        END IF;
    END LOOP;

    IF to_regclass('public.g2p_register_change_request_payloads') IS NOT NULL THEN
        INSERT INTO _r
        SELECT DISTINCT v
          FROM g2p_register_change_request_payloads p,
               jsonb_array_elements(CASE WHEN jsonb_typeof(p.change_payload::jsonb) = 'array'
                                         THEN p.change_payload::jsonb ELSE '[]'::jsonb END) e,
               LATERAL (SELECT e ->> 'geo_lowest_level_value_id'
                        UNION ALL SELECT e ->> 'woreda_level_value_id'
                        UNION ALL SELECT h ->> 'level_value_id'
                          FROM jsonb_array_elements(CASE WHEN jsonb_typeof(e -> 'geo_code_hierarchy_json' -> 'hierarchy') = 'array'
                                                         THEN e -> 'geo_code_hierarchy_json' -> 'hierarchy'
                                                         ELSE '[]'::jsonb END) h) ids(v)
         WHERE v IS NOT NULL
        ON CONFLICT DO NOTHING;
    END IF;
END $$;
SELECT id FROM _r ORDER BY id;
