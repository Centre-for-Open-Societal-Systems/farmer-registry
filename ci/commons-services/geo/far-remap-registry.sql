-- far, phase 2 of 3: point every farmer-registry record at the seed hierarchy.
-- Runs in the registry database (farmer_registry; farmer_registry_far on staging) inside the caller's transaction, after
-- seed-tables.sql and the seed rows (the registry has no geo tables; the seed is
-- the reference). The caller COMMITs or, on a dry run, ROLLs BACK.
--
-- Every location id the registry references gets exactly one target:
--   seed     already a seed id                      -> unchanged
--   pack     ETH pack id, which IS the P-code        -> <level>-<P-code>
--            (ET01 -> region-ET01, ET0101 -> zone-..., ET010101 -> woreda-...)
--   kamuntu  fictitious sample country (demo data)   -> a real kebele, picked
--            deterministically from md5(old id), so every table that shares an
--            old id lands on the same kebele and a re-run picks the same one
-- Anything else aborts: an id nobody can map is a question for a person.
--
-- Per mapped row, everything derived from the location is rewritten together:
-- geo_lowest_level_value_id, geo_code_hierarchy_json, woreda_level_value_id,
-- region/zone/woreda/kebele_name. Kamuntu's country code (KM) becomes ET in
-- every table that has a country_code. Tables are found through information_schema, not a hand list, so
-- register, history and intake-form tables are all covered. Change-request
-- payloads (record snapshots in JSON) get the same rewrite per element.

-- 1. Every referenced id.
CREATE TEMP TABLE _refs (old_id varchar PRIMARY KEY) ON COMMIT DROP;
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT c.table_name
               FROM information_schema.columns c
               JOIN information_schema.tables t
                 ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                AND t.table_type = 'BASE TABLE'
              WHERE c.table_schema = 'public' AND c.column_name = 'geo_lowest_level_value_id'
    LOOP
        EXECUTE format('INSERT INTO _refs SELECT DISTINCT geo_lowest_level_value_id FROM %I'
                       ' WHERE geo_lowest_level_value_id IS NOT NULL ON CONFLICT DO NOTHING',
                       r.table_name);
    END LOOP;

    IF to_regclass('public.g2p_register_change_request_payloads') IS NOT NULL THEN
        INSERT INTO _refs
        SELECT DISTINCT e ->> 'geo_lowest_level_value_id'
          FROM g2p_register_change_request_payloads p,
               jsonb_array_elements(CASE WHEN jsonb_typeof(p.change_payload::jsonb) = 'array'
                                         THEN p.change_payload::jsonb ELSE '[]'::jsonb END) e
         WHERE e ->> 'geo_lowest_level_value_id' IS NOT NULL
        ON CONFLICT DO NOTHING;
    END IF;
END $$;

-- 2. The mapping.
CREATE TEMP TABLE _kebeles ON COMMIT DROP AS
SELECT level_value_id, (row_number() OVER (ORDER BY level_value_id) - 1)::int AS i
  FROM _seed_values
 WHERE level_id = 'level-kebele';

CREATE TEMP TABLE _map ON COMMIT DROP AS
SELECT r.old_id,
       CASE
           WHEN s.level_value_id IS NOT NULL      THEN r.old_id
           WHEN r.old_id ~ '^ET[0-9]{2}$'         THEN 'region-' || r.old_id
           WHEN r.old_id ~ '^ET[0-9]{4}$'         THEN 'zone-' || r.old_id
           WHEN r.old_id ~ '^ET[0-9]{6}$'         THEN 'woreda-' || r.old_id
           WHEN r.old_id ILIKE 'kamuntu%'         THEN
               (SELECT k.level_value_id FROM _kebeles k
                 WHERE k.i = mod(('x' || substr(md5(r.old_id), 1, 7))::bit(28)::int,
                                 (SELECT count(*) FROM _kebeles)::int))
       END::varchar AS new_id,
       CASE
           WHEN s.level_value_id IS NOT NULL      THEN 'seed'
           WHEN r.old_id ~ '^ET[0-9]+$'           THEN 'pack'
           WHEN r.old_id ILIKE 'kamuntu%'         THEN 'kamuntu'
           ELSE 'unknown'
       END AS how
  FROM _refs r
  LEFT JOIN _seed_values s ON s.level_value_id = r.old_id;
ALTER TABLE _map ADD PRIMARY KEY (old_id);

DO $$
DECLARE
    bad text;
BEGIN
    SELECT string_agg(format('%s (%s)', old_id, how), ', ')
      INTO bad
      FROM (SELECT m.old_id, m.how FROM _map m
             WHERE m.new_id IS NULL
                OR NOT EXISTS (SELECT 1 FROM _seed_values s WHERE s.level_value_id = m.new_id)
             ORDER BY 1 LIMIT 30) x;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'no target in the seed for location id(s): %', bad;
    END IF;
END $$;

SELECT 'mapping', how, count(*) FROM _map GROUP BY how ORDER BY how;
-- The full old -> new list, for the build log: it is the audit trail of this run.
SELECT 'map', how, old_id, new_id FROM _map WHERE how <> 'seed' ORDER BY how, old_id;

-- 3. What each target location expands to.
CREATE TEMP TABLE _loc ON COMMIT DROP AS
WITH RECURSIVE chain AS (
    SELECT t.new_id AS id, s.level_value_id AS node, s.parent_level_value_id AS parent, 0 AS depth
      FROM (SELECT DISTINCT new_id FROM _map) t
      JOIN _seed_values s ON s.level_value_id = t.new_id
    UNION ALL
    SELECT c.id, p.level_value_id, p.parent_level_value_id, c.depth + 1
      FROM chain c
      JOIN _seed_values p ON p.level_value_id = c.parent
     WHERE c.depth < 10
)
-- Same shape as the records the staff portal writes.
SELECT c.id,
       jsonb_build_object(
           'hierarchy', jsonb_agg(jsonb_build_object(
               'level', l.level_mnemonic,
               'level_id', s.level_id,
               'level_mnemonic', l.level_mnemonic,
               'level_value_id', s.level_value_id,
               'level_value_mnemonic', s.level_value_mnemonic) ORDER BY c.depth DESC),
           'lowest_level_value_id', c.id) AS hierarchy,
       max(s.display_name)   FILTER (WHERE l.level_mnemonic = 'region') AS region_name,
       max(s.display_name)   FILTER (WHERE l.level_mnemonic = 'zone')   AS zone_name,
       max(s.display_name)   FILTER (WHERE l.level_mnemonic = 'woreda') AS woreda_name,
       max(s.display_name)   FILTER (WHERE l.level_mnemonic = 'kebele') AS kebele_name,
       max(s.level_value_id) FILTER (WHERE l.level_mnemonic = 'woreda') AS woreda_id
  FROM chain c
  JOIN _seed_values s ON s.level_value_id = c.node
  JOIN _seed_levels l ON l.level_id = s.level_id
 GROUP BY c.id;
ALTER TABLE _loc ADD PRIMARY KEY (id);

-- 4. Rewrite the tables.
CREATE TEMP TABLE _changed (table_name text, n bigint) ON COMMIT DROP;
DO $$
DECLARE
    r    record;
    sets text;
    n    bigint;
BEGIN
    FOR r IN SELECT c.table_name
               FROM information_schema.columns c
               JOIN information_schema.tables t
                 ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                AND t.table_type = 'BASE TABLE'
              WHERE c.table_schema = 'public' AND c.column_name = 'geo_lowest_level_value_id'
              ORDER BY 1
    LOOP
        -- Each derived column only where this table has it.
        SELECT 'geo_lowest_level_value_id = m.new_id' || coalesce(string_agg(
                   CASE column_name
                       WHEN 'geo_code_hierarchy_json' THEN format(', %I = n.hierarchy::%s', column_name, data_type)
                       WHEN 'woreda_level_value_id'   THEN ', woreda_level_value_id = n.woreda_id'
                       ELSE format(', %I = n.%I', column_name, column_name)
                   END, '' ORDER BY column_name), '')
          INTO sets
          FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = r.table_name
           AND column_name IN ('geo_code_hierarchy_json', 'woreda_level_value_id',
                               'region_name', 'zone_name', 'woreda_name', 'kebele_name');

        EXECUTE format('UPDATE %I t SET %s FROM _map m JOIN _loc n ON n.id = m.new_id'
                       ' WHERE t.geo_lowest_level_value_id = m.old_id AND m.how <> ''seed''',
                       r.table_name, sets);
        GET DIAGNOSTICS n = ROW_COUNT;
        INSERT INTO _changed VALUES (r.table_name, n);
    END LOOP;
END $$;

-- Record snapshots inside change requests: same rewrite, per array element, and
-- only the keys the element already carries.
CREATE FUNCTION pg_temp.geo_patch(e jsonb) RETURNS jsonb LANGUAGE sql AS $$
    SELECT CASE WHEN m.old_id IS NULL THEN e ELSE
               e || jsonb_build_object('geo_lowest_level_value_id', m.new_id)
                 || CASE WHEN e ? 'geo_code_hierarchy_json' THEN jsonb_build_object('geo_code_hierarchy_json', n.hierarchy) ELSE '{}' END
                 || CASE WHEN e ? 'woreda_level_value_id'   THEN jsonb_build_object('woreda_level_value_id', n.woreda_id)   ELSE '{}' END
                 || CASE WHEN e ? 'region_name'             THEN jsonb_build_object('region_name', n.region_name)          ELSE '{}' END
                 || CASE WHEN e ? 'zone_name'               THEN jsonb_build_object('zone_name', n.zone_name)              ELSE '{}' END
                 || CASE WHEN e ? 'woreda_name'             THEN jsonb_build_object('woreda_name', n.woreda_name)          ELSE '{}' END
                 || CASE WHEN e ? 'kebele_name'             THEN jsonb_build_object('kebele_name', n.kebele_name)          ELSE '{}' END
                 || CASE WHEN e ? 'country_code' AND m.how = 'kamuntu' THEN jsonb_build_object('country_code', 'ET') ELSE '{}' END
           END
      FROM (SELECT 1) one
      LEFT JOIN _map m ON m.old_id = e ->> 'geo_lowest_level_value_id' AND m.how <> 'seed'
      LEFT JOIN _loc n ON n.id = m.new_id
$$;

DO $$
DECLARE
    col_type text;
    n        bigint;
BEGIN
    SELECT data_type INTO col_type
      FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = 'g2p_register_change_request_payloads'
       AND column_name = 'change_payload';
    IF col_type IS NULL THEN
        RETURN;
    END IF;
    EXECUTE format(
        'UPDATE g2p_register_change_request_payloads p'
        '   SET change_payload = (SELECT jsonb_agg(pg_temp.geo_patch(a.e) ORDER BY a.i)'
        '                           FROM jsonb_array_elements(p.change_payload::jsonb) WITH ORDINALITY a(e, i))::%s'
        ' WHERE jsonb_typeof(p.change_payload::jsonb) = ''array'''
        '   AND EXISTS (SELECT 1 FROM jsonb_array_elements(p.change_payload::jsonb) e'
        '                 JOIN _map m ON m.old_id = e ->> ''geo_lowest_level_value_id'' AND m.how <> ''seed'')',
        col_type);
    GET DIAGNOSTICS n = ROW_COUNT;
    INSERT INTO _changed VALUES ('g2p_register_change_request_payloads', n);
END $$;

-- Kamuntu's country code, everywhere: on the remapped rows and on rows with no
-- location of their own (phones, household members).
DO $$
DECLARE
    r record;
    n bigint;
BEGIN
    FOR r IN SELECT c.table_name
               FROM information_schema.columns c
               JOIN information_schema.tables t
                 ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                AND t.table_type = 'BASE TABLE'
              WHERE c.table_schema = 'public' AND c.column_name = 'country_code'
              ORDER BY 1
    LOOP
        EXECUTE format('UPDATE %I SET country_code = ''ET'' WHERE country_code IN (''KM'', ''XKM'')', r.table_name);
        GET DIAGNOSTICS n = ROW_COUNT;
        IF n > 0 THEN
            INSERT INTO _changed VALUES (r.table_name || ' (country_code KM -> ET)', n);
        END IF;
    END LOOP;
END $$;

SELECT 'rewritten', table_name, n FROM _changed WHERE n > 0 ORDER BY table_name;

-- 5. Postconditions: every reference resolves in the seed.
DO $$
DECLARE
    r   record;
    bad text;
BEGIN
    FOR r IN SELECT c.table_name, c.column_name
               FROM information_schema.columns c
               JOIN information_schema.tables t
                 ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                AND t.table_type = 'BASE TABLE'
              WHERE c.table_schema = 'public'
                AND c.column_name IN ('geo_lowest_level_value_id', 'woreda_level_value_id')
    LOOP
        EXECUTE format('SELECT string_agg(DISTINCT x.%1$I, '', '') FROM %2$I x'
                       ' WHERE x.%1$I IS NOT NULL'
                       '   AND NOT EXISTS (SELECT 1 FROM _seed_values s WHERE s.level_value_id = x.%1$I)',
                       r.column_name, r.table_name)
          INTO bad;
        IF bad IS NOT NULL THEN
            RAISE EXCEPTION '%.% still references ids outside the seed: %', r.table_name, r.column_name, left(bad, 500);
        END IF;
    END LOOP;
END $$;
