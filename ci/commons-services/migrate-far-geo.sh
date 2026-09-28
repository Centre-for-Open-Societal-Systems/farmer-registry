#!/bin/sh
# One-time move of the far namespace's Master Data from the chart's ETH country
# pack (ids = bare P-codes, levels l0..l4) plus the fictitious Kamuntu sample
# country onto the Ethiopia hierarchy the other registries use (ids
# <level>-<P-code>, region > zone > woreda > kebele), with every farmer-registry
# record remapped and no Kamuntu data left in either database. See
# docs/commons-services-upgrade.md, "Location hierarchy".
#
#   KUBECONFIG=... DRY_RUN=true ci/commons-services/migrate-far-geo.sh
#
# Three transactions, in this order so that every id the registry references
# resolves at every moment:
#   1. master_data      rename the old levels to legacy_*, load the seed next to them
#   2. farmer_registry  remap every record to the seed (geo/far-remap-registry.sql)
#   3. master_data      delete the legacy_* hierarchy, once the registry no longer
#                       references any of it
# Each aborts as a whole on any guard. A failed run can be re-run: phases that
# already committed are no-ops the second time.
#
# DRY_RUN defaults to true: phases 1 and 2 run to the end and roll back, and the
# mapping they would apply is printed; phase 3 is only described, since its guard
# needs phase 2 committed. Before a real run both databases' affected tables are
# dumped to ./far-geo-backup-*.sql.gz (archived by the Jenkins job).
#
# Afterwards, in the registry: re-run the farmer db-seed hook (syncGeoWidgets
# re-matches the intake form's Location widget to the new levels) and refresh the
# fr_rpt_* reporting views. Both are listed at the end of the run.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/geo-common.sh"

[ -n "$REGISTRY_DB" ] || { echo "no registry database for namespace $NAMESPACE; set REGISTRY_DB" >&2; exit 1; }

lint_seed
readings before

if [ "$DRY_RUN" = "false" ]; then
    STAMP=$(date -u +%Y%m%dT%H%M%SZ)
    echo "=== backup: master_data geo tables ==="
    kubectl exec -n "$NAMESPACE" "$PG_POD" -- sh -c \
        'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -U postgres -d "$1" -t public.g2p_geo_levels -t public.g2p_geo_level_values' \
        _ "$MD_DB" | gzip > "far-geo-backup-$MD_DB-$STAMP.sql.gz"
    echo "=== backup: $REGISTRY_DB register, history, intake-form and change-request tables ==="
    kubectl exec -n "$NAMESPACE" "$PG_POD" -- sh -c \
        'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -U postgres -d "$1" -t "public.g2p_register_*" -t "public.g2p_intake_form_*"' \
        _ "$REGISTRY_DB" | gzip > "far-geo-backup-$REGISTRY_DB-$STAMP.sql.gz"
    ls -l far-geo-backup-*"$STAMP".sql.gz
fi

echo "=== phase 1/3: $MD_DB -- retire old level names, load the seed alongside (DRY_RUN=$DRY_RUN) ==="
{
    echo "BEGIN;"
    schema_topup
    cat "$GEO/seed-tables.sql"
    seed_rows
    cat "$GEO/far-retire-levels.sql"
    cat "$GEO/seed-apply.sql"
    end_tx
} | pg "$MD_DB"

echo "=== phase 2/3: $REGISTRY_DB -- remap every record to the seed (DRY_RUN=$DRY_RUN) ==="
{
    echo "BEGIN;"
    cat "$GEO/seed-tables.sql"
    seed_rows
    cat "$GEO/far-remap-registry.sql"
    cat "$GEO/kamuntu-scan.sql"
    cat "$GEO/kamuntu-guard.sql"
    end_tx
} | pg "$REGISTRY_DB"

echo "=== phase 3/3: $MD_DB -- delete the legacy hierarchy (DRY_RUN=$DRY_RUN) ==="
if [ "$DRY_RUN" = "false" ]; then
    REFS=$({ echo "BEGIN;"; cat "$GEO/registry-refs.sql"; echo "ROLLBACK;"; } | pg "$REGISTRY_DB")
    {
        echo "BEGIN;"
        echo "CREATE TEMP TABLE _refs (old_id varchar PRIMARY KEY) ON COMMIT DROP;"
        echo "COPY _refs FROM STDIN;"
        [ -z "$REFS" ] || printf '%s\n' "$REFS"
        printf '%s\n' '\.'
        cat "$GEO/far-drop-legacy.sql"
        cat "$GEO/kamuntu-scan.sql"
        cat "$GEO/kamuntu-guard.sql"
        end_tx
    } | pg "$MD_DB"
else
    # Nothing to rehearse against: phase 2 did not commit, so the registry still
    # references the old ids and the guard would (correctly) refuse.
    echo "skipped on a dry run; it would delete every location under these levels:"
    echo "SELECT 'would drop', l.level_id, l.level_mnemonic, count(v.level_value_id)
            FROM g2p_geo_levels l LEFT JOIN g2p_geo_level_values v USING (level_id)
           WHERE l.level_id NOT IN ('level-region', 'level-zone', 'level-woreda', 'level-kebele')
           GROUP BY 2, 3 ORDER BY 2;" | pg "$MD_DB"
fi

readings after
if [ "$DRY_RUN" = "false" ]; then
    cat <<EOF
=== done. Still to do in the registry ===
  1. Re-run the farmer-registry db-seed hook (the registry pipeline's deploy), so
     syncGeoWidgets matches the intake form's Location widget to the new levels.
  2. Refresh the fr_rpt_* reporting views (docs/reporting-refresh-log.md).
  3. Deploy commons-services with values-far.yaml (geoSeed.load.geo: false), or
     the next upgrade's ETH-pack hook will fail on the level names.
EOF
else
    echo "=== DRY RUN: rolled back, nothing was changed ==="
fi
