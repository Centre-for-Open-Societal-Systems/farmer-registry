-- far, phase 1 of 3 (part): move the old hierarchy's level names out of the way.
-- Runs in master_data after the seed rows are staged and before seed-apply.sql,
-- in the same transaction.
--
-- level_mnemonic is UNIQUE, and the chart's ETH country pack holds country,
-- region, zone, woreda (and village, from Kamuntu) under level ids l0..l4. The
-- seed needs region/zone/woreda/kebele under its own level ids. Renaming the old
-- ones to legacy_* lets both hierarchies exist side by side, so every id the
-- registry references keeps resolving while phase 2 remaps the records. Phase 3
-- deletes the legacy_* levels and their locations.
--
-- "Old" means any level the seed does not define -- not a hard-coded l0..l4 --
-- so an environment whose pack used other level ids is handled the same way.
SELECT 'retire level', level_id, level_mnemonic, 'legacy_' || level_mnemonic
  FROM g2p_geo_levels
 WHERE level_id NOT IN (SELECT level_id FROM _seed_levels)
   AND level_mnemonic NOT LIKE 'legacy\_%'
 ORDER BY level_id;

UPDATE g2p_geo_levels
   SET level_mnemonic = 'legacy_' || level_mnemonic
 WHERE level_id NOT IN (SELECT level_id FROM _seed_levels)
   AND level_mnemonic NOT LIKE 'legacy\_%';
