#!/bin/sh
# Builds fr_rpt_geo_levels: this deployment's geo level names, so a dashboard
# can title the positional geo_1..geo_N columns of the other reporting views.
#
# The names come from Master Data, which holds the country pack and is seeded
# before the registry, so the lookup is right on an empty install too. The view
# itself is a VALUES list: it is a handful of rows of metadata, it must exist
# before any data does, and nothing should have to refresh it.
#
# Registry connection: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD.
# Master Data: MDS_DB, MDS_PGUSER, MDS_PGPASSWORD, plus MDS_PGHOST / MDS_PGPORT
# when it is not on the registry's Postgres. Master Data is a separate database
# owned by a separate role, so it is read with its own credentials.
set -eu

# Ordered by walking parent -> child, never by level_id: the ids are opaque and
# their sort order is not the hierarchy. Each row comes back as a ready SQL
# VALUES tuple, quoted by Postgres itself.
levels=$(
    PGHOST="${MDS_PGHOST:-$PGHOST}" \
    PGPORT="${MDS_PGPORT:-$PGPORT}" \
    PGDATABASE="$MDS_DB" \
    PGUSER="$MDS_PGUSER" \
    PGPASSWORD="$MDS_PGPASSWORD" \
    psql -v ON_ERROR_STOP=1 -At <<'SQL'
WITH RECURSIVE chain AS (
    SELECT level_id, level_mnemonic, 1 AS depth
    FROM g2p_geo_levels
    WHERE parent_level_id IS NULL
    UNION ALL
    SELECT l.level_id, l.level_mnemonic, c.depth + 1
    FROM g2p_geo_levels l
    JOIN chain c ON l.parent_level_id = c.level_id
    WHERE c.depth < 20
)
SELECT format('(%s, %L)', depth, level_mnemonic) FROM chain ORDER BY depth;
SQL
)

if [ -z "$levels" ]; then
    echo "[reporting-views] ERROR: Master Data ($MDS_DB) has no geo hierarchy." >&2
    echo "[reporting-views] Seed Master Data first; fr_rpt_geo_levels is left unchanged." >&2
    exit 1
fi

# A level with two children would give two rows the same depth, and the
# dashboards would title a column with whichever came first.
depths=$(printf '%s\n' "$levels" | cut -d, -f1 | sort | uniq -d)
if [ -n "$depths" ]; then
    echo "[reporting-views] ERROR: Master Data's geo hierarchy branches; expected one level per depth." >&2
    printf '%s\n' "$levels" >&2
    exit 1
fi

values=$(printf '%s\n' "$levels" | paste -sd, -)
echo "[reporting-views] geo levels from Master Data: $values"

psql -v ON_ERROR_STOP=1 <<SQL
CREATE OR REPLACE VIEW fr_rpt_geo_levels AS
    SELECT depth, level_name FROM (VALUES $values) AS t(depth, level_name);
COMMENT ON VIEW fr_rpt_geo_levels IS
    'Geo level name per depth, from Master Data. Titles geo_N in the fr_rpt_ views.';
SQL
