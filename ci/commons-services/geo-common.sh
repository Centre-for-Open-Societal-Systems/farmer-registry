# Shared by seed-locations.sh and migrate-far-geo.sh. Sourced, not run.
#
# Everything runs through psql inside the namespace's Postgres pod, as the
# superuser: it is the one place that reaches both master_data and the
# registry's own database, and it needs nothing copied out of the cluster.
#
# Expects HERE (the directory of the calling script) to be set.

NAMESPACE="${NAMESPACE:-far}"
PG_POD="${PG_POD:-commons-postgresql-0}"
MD_DB="${MD_DB:-master_data}"
# Default: rehearse. Every transaction runs to the end, guards included, and
# then rolls back. Set DRY_RUN=false to commit.
DRY_RUN="${DRY_RUN:-true}"
GEO="$HERE/geo"
# The one source of truth for the hierarchy: the same file the local stack
# loads (docker-compose.yml, farmer-registry-geo-seed).
SEED_GZ="${SEED_GZ:-$HERE/../../docker/local-dev/geo-seed/ethiopia_geo_seed.sql.gz}"

case "$NAMESPACE" in
    far)  _registry_db=farmer_registry ;;
    crop) _registry_db=cropsown_registry ;;
    live) _registry_db=livestock_registry ;;
    *)    _registry_db= ;;
esac
# Set it empty to skip the registry readings.
REGISTRY_DB="${REGISTRY_DB-$_registry_db}"

: "${KUBECONFIG:?set KUBECONFIG to the kubeconfig of the target cluster}"

# pg DB -- run the SQL on stdin in DB. Quiet (no command tags, so 21k INSERTs
# print nothing), unaligned, stops at the first error. The Bitnami image sets
# POSTGRESQL_CLIENT_MIN_MESSAGES, which hides NOTICEs, so everything meant for
# the log is a SELECT.
pg() {
    kubectl exec -i -n "$NAMESPACE" "$PG_POD" -- sh -c \
        'PGOPTIONS="-c client_min_messages=warning" PGPASSWORD="$POSTGRES_PASSWORD" exec psql -U postgres -d "$1" -X -q -A -t -F " | " -v ON_ERROR_STOP=1' \
        _ "$1"
}

# The transaction's last statement.
end_tx() {
    if [ "$DRY_RUN" = "false" ]; then
        echo "COMMIT;"
    else
        echo "ROLLBACK;"
    fi
}

# The seed's INSERTs, retargeted at the _seed_* temp tables (geo/seed-tables.sql).
# The seed's own BEGIN/COMMIT are dropped: the caller owns the transaction.
seed_rows() {
    gzip -dc "$SEED_GZ" | sed \
        -e '/^BEGIN;$/d' -e '/^COMMIT;$/d' \
        -e 's/^INSERT INTO public\.g2p_geo_levels /INSERT INTO _seed_levels /' \
        -e 's/^INSERT INTO public\.g2p_geo_level_values /INSERT INTO _seed_values /'
}

# master-data-schema-topup.sql without its own BEGIN/COMMIT, so it runs inside
# the caller's transaction (and rolls back with it on a dry run). A Master Data
# built before the 1.1.0 models (the live namespace's) has no display_name,
# pcode, ... columns, which the seed writes.
schema_topup() {
    sed -e '/^BEGIN;/d' -e '/^COMMIT;/d' "$HERE/master-data-schema-topup.sql"
}

# Refuse a seed that could do anything but insert into the staging tables.
lint_seed() {
    [ -f "$SEED_GZ" ] || { echo "seed not found: $SEED_GZ" >&2; exit 1; }
    BAD=$(seed_rows | grep -v -E '^(--|$|INSERT INTO _seed_(levels|values) )' | head -5 || true)
    if [ -n "$BAD" ]; then
        echo "seed contains statements other than INSERTs into the geo tables:" >&2
        echo "$BAD" >&2
        exit 1
    fi
    # ...and every one of them must only ever insert: DO NOTHING on conflict,
    # never DO UPDATE, so an existing location is never rewritten by the seed.
    BAD=$(seed_rows | grep '^INSERT' | grep -v -E ' ON CONFLICT \((level_id|level_value_id)\) DO NOTHING;$' | head -5 || true)
    if [ -n "$BAD" ]; then
        echo "seed INSERTs must end in ON CONFLICT (...) DO NOTHING:" >&2
        echo "$BAD" >&2
        exit 1
    fi
    echo "=== seed: $(seed_rows | grep -c '^INSERT INTO _seed_values ') locations, $(seed_rows | grep -c '^INSERT INTO _seed_levels ') levels, inserts only ==="
}

# Read-only readings of master_data and, when there is one, the registry.
readings() {
    echo "=== readings ($1): $NAMESPACE/$MD_DB ==="
    pg "$MD_DB" < "$GEO/mds-readings.sql"
    { echo "BEGIN;"; cat "$GEO/kamuntu-scan.sql"
      echo "SELECT 'kamuntu', table_name || '.' || column_name, n FROM _kamuntu_hits ORDER BY 2;"
      echo "ROLLBACK;"; } | pg "$MD_DB"
    if [ -n "$REGISTRY_DB" ]; then
        echo "=== readings ($1): $NAMESPACE/$REGISTRY_DB ==="
        pg "$REGISTRY_DB" < "$GEO/registry-readings.sql"
        { echo "BEGIN;"; cat "$GEO/kamuntu-scan.sql"
          echo "SELECT 'kamuntu', table_name || '.' || column_name, n FROM _kamuntu_hits ORDER BY 2;"
          echo "ROLLBACK;"; } | pg "$REGISTRY_DB"
    fi
}
