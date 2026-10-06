-- Apply the location seed (already in _seed_levels / _seed_values) to Master
-- Data. Runs inside the caller's transaction, after seed-tables.sql and the
-- seed rows; the caller COMMITs or, on a dry run, ROLLs BACK.
--
-- Additive only: a location that already exists keeps its id, level, parent,
-- names and every other column.
--
-- Every guard aborts the whole transaction: nothing is half-applied.

-- 0. Seed corrections. The special woredas (Kebena, Mareko, Tembaro) were
-- first seeded with no parent, so their zone listed no woredas and the
-- Location cascade stopped at Zone. A Master Data loaded before the
-- seed was corrected still holds those NULLs, and the parent guard below
-- would then refuse every later run. Fill a NULL parent from the seed -- only
-- a NULL, and only with a parent row that exists here under the seed's id, so
-- a name-keyed hierarchy (livestock's) is not touched and still trips the
-- guard as before.
UPDATE g2p_geo_level_values v
   SET parent_level_value_id = s.parent_level_value_id
  FROM _seed_values s
 WHERE v.level_value_id = s.level_value_id
   AND v.parent_level_value_id IS NULL
   AND s.parent_level_value_id IS NOT NULL
   AND EXISTS (SELECT 1
                 FROM g2p_geo_level_values p
                 JOIN _seed_values sp ON sp.level_value_id = p.level_value_id
                WHERE p.level_value_id = s.parent_level_value_id
                  -- the parent is linked the seed's way too (by id, not name)
                  AND p.parent_level_value_id IS NOT DISTINCT FROM sp.parent_level_value_id);

-- 1. Preconditions.
DO $$
DECLARE
    bad text;
BEGIN
    -- The seed's level names (region, zone, woreda, kebele) are UNIQUE in
    -- g2p_geo_levels. If another level already holds one -- the chart's ETH
    -- country pack does, as l1..l3 -- inserting ours would fail half way, and
    -- the two hierarchies could not coexist anyway.
    SELECT string_agg(format('%s (seed level %s, existing level %s)',
                             s.level_mnemonic, s.level_id, l.level_id), '; ')
      INTO bad
      FROM _seed_levels s
      JOIN g2p_geo_levels l ON l.level_mnemonic = s.level_mnemonic AND l.level_id <> s.level_id;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'level name already used by another level: %. In the far namespace run migrate-far-geo.sh first.', bad;
    END IF;

    -- An existing location with a seed id but at another level would mean the
    -- id means something else here. Never overwrite that.
    SELECT string_agg(level_value_id, ', ')
      INTO bad
      FROM (SELECT v.level_value_id
              FROM _seed_values s
              JOIN g2p_geo_level_values v USING (level_value_id)
             WHERE v.level_id <> s.level_id
             ORDER BY 1 LIMIT 20) x;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'existing locations sit at a different level than the seed says: %', bad;
    END IF;

    -- A parent that differs from the seed's means this Master Data keys its
    -- hierarchy differently. The `live` namespace does, on purpose: the
    -- livestock registry's own db-seed loads a variant whose parent links are
    -- the parent's NAME, with names unique, because its Location widget cascades
    -- by name (see the header of livestock-registry's
    -- docker/db-seed/geo/ethiopia_geo_seed.sql.gz). Mixing id-keyed rows into
    -- that would break its dropdowns, so stop.
    SELECT string_agg(level_value_id, ', ')
      INTO bad
      FROM (SELECT v.level_value_id
              FROM _seed_values s
              JOIN g2p_geo_level_values v USING (level_value_id)
             WHERE v.parent_level_value_id IS DISTINCT FROM s.parent_level_value_id
             ORDER BY 1 LIMIT 20) x;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'existing locations have a different parent than the seed (a name-keyed hierarchy, like livestock''s?): %', bad;
    END IF;
END $$;

-- 2. What this run changes, for the log.
SELECT 'change', 'levels to add', count(*)
  FROM _seed_levels s
 WHERE NOT EXISTS (SELECT 1 FROM g2p_geo_levels l WHERE l.level_id = s.level_id);
SELECT 'change', 'locations to add', count(*)
  FROM _seed_values s
 WHERE NOT EXISTS (SELECT 1 FROM g2p_geo_level_values v WHERE v.level_value_id = s.level_value_id);

-- 3. Apply.
INSERT INTO g2p_geo_levels
    (level_id, level_mnemonic, parent_level_id, display_name, display_name_i18n,
     version, valid_from, valid_to)
SELECT level_id, level_mnemonic, parent_level_id, display_name, display_name_i18n,
       version, valid_from, valid_to
  FROM _seed_levels
ON CONFLICT (level_id) DO NOTHING;

INSERT INTO g2p_geo_level_values
    (level_value_id, level_id, level_value_mnemonic, parent_level_value_id, pcode,
     pcode_source, boundary_uri, boundary_simplified_uri, display_name,
     display_name_i18n, version, valid_from, valid_to)
SELECT level_value_id, level_id, level_value_mnemonic, parent_level_value_id, pcode,
       pcode_source, boundary_uri, boundary_simplified_uri, display_name,
       display_name_i18n, version, valid_from, valid_to
  FROM _seed_values
ON CONFLICT (level_value_id) DO NOTHING;

-- 4. Postconditions.
DO $$
DECLARE
    n bigint;
BEGIN
    SELECT count(*) INTO n
      FROM _seed_values s
     WHERE NOT EXISTS (SELECT 1 FROM g2p_geo_level_values v WHERE v.level_value_id = s.level_value_id);
    IF n > 0 THEN
        RAISE EXCEPTION '% seed location(s) missing after the load', n;
    END IF;

    SELECT count(*) INTO n
      FROM g2p_geo_level_values v
     WHERE v.parent_level_value_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM g2p_geo_level_values p
                        WHERE p.level_value_id = v.parent_level_value_id);
    IF n > 0 THEN
        RAISE EXCEPTION '% location(s) point at a parent that does not exist', n;
    END IF;
END $$;
