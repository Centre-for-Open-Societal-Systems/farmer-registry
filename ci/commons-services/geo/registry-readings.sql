-- Which id scheme the registry's records point at, per table. Read-only.
--   seed     region-ET01 / zone-ET0101 / woreda-... / kebele-...  (the target)
--   pack     ET01 / ET0101 / ET010101  (the chart's ETH country pack)
--   kamuntu  kamuntu/...               (the fictitious sample country)
--   other    anything else -- migrate-far-geo.sh refuses to guess these
SELECT 'references', table_name, scheme, n
  FROM (SELECT c.table_name, k.scheme,
               (xpath('/row/n/text()', query_to_xml(format(
                   'SELECT count(*) AS n FROM %I WHERE %s', c.table_name,
                   CASE k.scheme
                       WHEN 'seed'    THEN 'geo_lowest_level_value_id ~ ''^(region|zone|woreda|kebele)-'''
                       WHEN 'pack'    THEN 'geo_lowest_level_value_id ~ ''^ET[0-9]*$'''
                       WHEN 'kamuntu' THEN 'geo_lowest_level_value_id ILIKE ''kamuntu%'''
                       ELSE 'geo_lowest_level_value_id !~ ''^(region|zone|woreda|kebele)-'''
                            ' AND geo_lowest_level_value_id !~ ''^ET[0-9]*$'''
                            ' AND geo_lowest_level_value_id NOT ILIKE ''kamuntu%'''
                   END), false, true, '')))[1]::text::bigint AS n
          FROM information_schema.columns c
          JOIN information_schema.tables t
            ON t.table_schema = c.table_schema AND t.table_name = c.table_name
           AND t.table_type = 'BASE TABLE'
         CROSS JOIN (VALUES ('seed'), ('pack'), ('kamuntu'), ('other')) k(scheme)
         WHERE c.table_schema = 'public'
           AND c.column_name = 'geo_lowest_level_value_id') x
 WHERE n > 0
 ORDER BY table_name, scheme;
