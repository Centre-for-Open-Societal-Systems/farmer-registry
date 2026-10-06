-- far, phase 3 of 3: delete the old hierarchy (the legacy_* levels phase 1
-- renamed -- the ETH pack plus the Kamuntu sample country) once nothing points
-- at it. Runs in master_data inside the caller's transaction; the caller has
-- loaded _refs(old_id) with every id the registry references (registry-refs.sql).
--
-- The only DELETE in this change, and it is scoped by the legacy_* levels, never
-- by "everything not in the seed": a location someone added by hand under a
-- seed level is not touched.

DO $$
DECLARE
    bad text;
BEGIN
    SELECT string_agg(old_id, ', ')
      INTO bad
      FROM (SELECT r.old_id
              FROM _refs r
             WHERE NOT EXISTS (SELECT 1
                                 FROM g2p_geo_level_values v
                                 JOIN g2p_geo_levels l ON l.level_id = v.level_id
                                WHERE v.level_value_id = r.old_id
                                  AND l.level_mnemonic NOT LIKE 'legacy\_%')
             ORDER BY 1 LIMIT 30) x;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'the registry still references locations outside the seed hierarchy: %. Run phase 2 (remap) first.', bad;
    END IF;
END $$;

SELECT 'drop', 'legacy locations', count(*)
  FROM g2p_geo_level_values
 WHERE level_id IN (SELECT level_id FROM g2p_geo_levels WHERE level_mnemonic LIKE 'legacy\_%');
SELECT 'drop', 'legacy levels', string_agg(level_id || '=' || level_mnemonic, ', ' ORDER BY level_id)
  FROM g2p_geo_levels
 WHERE level_mnemonic LIKE 'legacy\_%';

DELETE FROM g2p_geo_level_values
 WHERE level_id IN (SELECT level_id FROM g2p_geo_levels WHERE level_mnemonic LIKE 'legacy\_%');
DELETE FROM g2p_geo_levels
 WHERE level_mnemonic LIKE 'legacy\_%';

DO $$
DECLARE
    n bigint;
BEGIN
    SELECT count(*) INTO n
      FROM g2p_geo_level_values v
     WHERE v.parent_level_value_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM g2p_geo_level_values p
                        WHERE p.level_value_id = v.parent_level_value_id);
    IF n > 0 THEN
        RAISE EXCEPTION '% location(s) would be left pointing at a deleted parent', n;
    END IF;
END $$;
