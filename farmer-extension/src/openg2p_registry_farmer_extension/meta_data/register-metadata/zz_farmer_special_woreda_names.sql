-- Region / Zone for records on the three special woredas.
--
-- Kebena, Mareko and Tembaro SP woredas were loaded into Master Data with no
-- parent zone. A farmer saved on one of them got its flattened location names
-- from that broken hierarchy: woreda and kebele, but region_name and zone_name
-- NULL -- the farmer list shows an empty Region and Zone. The seed and its
-- loaders now give the woredas their parents, but the registry keeps no
-- location tables of its own, so these names are only recomputed when the
-- record's Location is saved again. This fills them for the records already
-- saved.
--
-- Names are the seed's (docker/db-seed/seed-data/geo/geo_level_values.json;
-- test/test_geo_seed_hierarchy.py keeps the two in step). Only NULLs are
-- filled, never a value someone set, so a re-run changes nothing. Tables are
-- found through information_schema -- register, history and intake-form
-- tables alike -- as far-remap-registry.sql does.
DO $$
DECLARE
    t record;
BEGIN
    FOR t IN
        SELECT c.table_name
          FROM information_schema.columns c
         WHERE c.table_schema = 'public'
           AND c.column_name IN ('woreda_name', 'zone_name', 'region_name')
         GROUP BY c.table_name
        HAVING count(*) = 3
    LOOP
        EXECUTE format(
            'UPDATE %I t
                SET region_name = coalesce(t.region_name, s.region_name),
                    zone_name   = coalesce(t.zone_name, s.zone_name)
               FROM (VALUES (''kebena sp woreda'',  ''Kebena Special'',  ''Central Ethiopia''),
                            (''mareko sp woreda'',  ''Mareko Special'',  ''Central Ethiopia''),
                            (''tembaro sp woreda'', ''Tembaro Special'', ''Central Ethiopia''))
                    AS s (woreda, zone_name, region_name)
              WHERE lower(trim(t.woreda_name)) = s.woreda
                AND (t.region_name IS NULL OR t.zone_name IS NULL)',
            t.table_name);
    END LOOP;
END $$;
