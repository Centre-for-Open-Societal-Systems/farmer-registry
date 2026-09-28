-- Master Data geo, as it stands. Read-only; printed before and after each run.
SELECT 'levels', string_agg(level_id || '=' || level_mnemonic, ', ' ORDER BY level_id)
  FROM g2p_geo_levels;
SELECT 'locations', level_id, count(*)
  FROM g2p_geo_level_values
 GROUP BY level_id
 ORDER BY level_id;
SELECT 'orphan parents', count(*)
  FROM g2p_geo_level_values v
 WHERE v.parent_level_value_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM g2p_geo_level_values p
                    WHERE p.level_value_id = v.parent_level_value_id);
