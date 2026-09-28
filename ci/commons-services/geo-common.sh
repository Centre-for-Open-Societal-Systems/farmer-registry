# Shared by seed-locations.sh and migrate-far-geo.sh. Sourced, not run.
#
# How the SQL reaches the databases
# ---------------------------------
# Not by exec'ing into the Postgres pod: on staging commons-postgresql-0 is in
# the `commons` namespace, where the Jenkins identity (far:farmer-ci, admin in
# `far` only) has no pods/exec, and it would need the superuser anyway.
#
# Instead each batch runs in a throwaway psql pod in the registry's namespace,
# connecting exactly the way the registry itself does: host, port, database,
# user and password secret are read off the registry's staff-portal-api
# Deployment, which carries both of its connections --
#   *_DB_*              its own database (farmer_registry on dev,
#                       farmer_registry_far on staging)
#   *_MASTER_DATA_DB_*  Master Data
# So nothing about an environment is hard-coded here, the same code works where
# Postgres lives in `far` (dev) and where it lives in `commons` (staging), and
# every statement runs as the application user that owns the tables.
#
# Expects HERE (the directory of the calling script) to be set.

NAMESPACE="${NAMESPACE:-far}"
case "$NAMESPACE" in
    far)  _release=farmer-registry ;;
    crop) _release=cropsown-registry ;;
    live) _release=livestock-registry ;;
    *)    _release= ;;
esac
REGISTRY_RELEASE="${REGISTRY_RELEASE:-$_release}"
# Carries psql and pg_dump 16, and is already pulled wherever the commons chart
# runs (it is the commons-postgresql server image).
PSQL_IMAGE="${PSQL_IMAGE:-docker.io/openg2p/postgresql:16.4.0-debian-12-r14}"
# Default: rehearse. Every transaction runs to the end, guards included, and
# then rolls back. Set DRY_RUN=false to commit.
DRY_RUN="${DRY_RUN:-true}"
GEO="$HERE/geo"
# The one source of truth for the hierarchy: the same file the local stack
# loads (docker-compose.yml, farmer-registry-geo-seed).
SEED_GZ="${SEED_GZ:-$HERE/../../docker/local-dev/geo-seed/ethiopia_geo_seed.sql.gz}"

: "${KUBECONFIG:?set KUBECONFIG to the kubeconfig of the target cluster}"
[ -n "$REGISTRY_RELEASE" ] || { echo "no registry release known for namespace $NAMESPACE; set REGISTRY_RELEASE" >&2; exit 1; }

# The registry API's env, one "NAME<TAB>value<TAB>secret<TAB>key" per line.
_API_ENV=$(kubectl get deploy "$REGISTRY_RELEASE-staff-portal-api" -n "$NAMESPACE" -o jsonpath='{range .spec.template.spec.containers[*].env[*]}{.name}{"\t"}{.value}{"\t"}{.valueFrom.secretKeyRef.name}{"\t"}{.valueFrom.secretKeyRef.key}{"\n"}{end}') || {
    echo "cannot read deploy/$REGISTRY_RELEASE-staff-portal-api in $NAMESPACE" >&2
    exit 1
}

# _conn KIND FIELD COLUMN -- one column of the connection setting FIELD
# (HOSTNAME, PORT, DBNAME, USERNAME, PASSWORD) for KIND md or registry.
_conn() {
    case "$1" in
        md)       _pat="_MASTER_DATA_DB_$2" ;;
        registry) _pat="_DB_$2" ;;
    esac
    printf '%s\n' "$_API_ENV" | awk -F '\t' -v p="$_pat" -v k="$1" -v c="$3" '
        substr($1, length($1) - length(p) + 1) == p &&
        (k == "md" || $1 !~ /_MASTER_DATA_DB_/) { print $c; exit }'
}

# _pod_env KIND PREFIX -- KIND's libpq settings as JSON env entries named
# <PREFIX>PGHOST ... <PREFIX>PGPASSWORD (the password by secret reference).
_pod_env() {
    _pw_secret=$(_conn "$1" PASSWORD 3)
    if [ -n "$_pw_secret" ]; then
        _pw="{\"name\":\"${2}PGPASSWORD\",\"valueFrom\":{\"secretKeyRef\":{\"name\":\"$_pw_secret\",\"key\":\"$(_conn "$1" PASSWORD 4)\"}}}"
    else
        _pw="{\"name\":\"${2}PGPASSWORD\",\"value\":\"$(_conn "$1" PASSWORD 2)\"}"
    fi
    printf '{"name":"%sPGHOST","value":"%s"},{"name":"%sPGPORT","value":"%s"},{"name":"%sPGDATABASE","value":"%s"},{"name":"%sPGUSER","value":"%s"},%s' \
        "$2" "$(_conn "$1" HOSTNAME 2)" "$2" "$(_conn "$1" PORT 2)" \
        "$2" "$(_conn "$1" DBNAME 2)" "$2" "$(_conn "$1" USERNAME 2)" "$_pw"
}

# One helper pod per run, holding both connections, deleted on exit. Commands
# go through `kubectl exec`, whose streams are reliable: `kubectl run --rm -i`
# was tried first and cut a pg_dump short mid-table with exit status 0.
# activeDeadlineSeconds ends it even if this script is killed before the trap.
_start_helper() {
    HELPER="geo-psql-$(date +%s)-$$"
    kubectl run "$HELPER" -n "$NAMESPACE" --image="$PSQL_IMAGE" --restart=Never --quiet \
        --overrides="{\"apiVersion\":\"v1\",\"metadata\":{\"annotations\":{\"sidecar.istio.io/inject\":\"false\"}},\"spec\":{\"activeDeadlineSeconds\":7200,\"containers\":[{\"name\":\"psql\",\"image\":\"$PSQL_IMAGE\",\"command\":[\"sleep\",\"7200\"],\"env\":[$(_pod_env md MD_),$(_pod_env registry REG_)]}]}}" \
        > /dev/null
    trap 'kubectl delete pod "$HELPER" -n "$NAMESPACE" --wait=false > /dev/null 2>&1 || true' EXIT
    kubectl wait --for=condition=Ready "pod/$HELPER" -n "$NAMESPACE" --timeout=5m > /dev/null
}

# _in_pod KIND CMD... -- run CMD in the helper pod with KIND's connection as the
# standard PG* variables, stdin attached; returns CMD's exit status.
_in_pod() {
    case "$1" in md) _p=MD_ ;; registry) _p=REG_ ;; esac
    shift
    kubectl exec -i -n "$NAMESPACE" "$HELPER" -- sh -c '
        p=$1; shift
        for v in PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD; do
            eval "export $v=\"\${$p$v}\""
        done
        export PGOPTIONS="-c client_min_messages=warning"
        exec "$@"' _ "$_p" "$@"
}

# pg KIND -- run the SQL on stdin against KIND (md | registry). Quiet (no
# command tags, so 21k INSERTs print nothing), unaligned, stops at the first
# error. NOTICEs are off; everything meant for the log is a SELECT.
pg() {
    _in_pod "$1" psql -X -q -A -t -F " | " -v ON_ERROR_STOP=1
}

# pg_dump_tables KIND PATTERN... -- pg_dump of the matching tables, to stdout.
pg_dump_tables() {
    _k=$1; shift
    _args=
    for _t in "$@"; do _args="$_args -t $_t"; done
    # Patterns contain * and must reach pg_dump unexpanded: no glob in the pod.
    _in_pod "$_k" sh -c 'set -f; exec pg_dump --no-owner --no-privileges $0' "$_args" < /dev/null
}

for _k in md registry; do
    for _f in HOSTNAME PORT DBNAME USERNAME PASSWORD; do
        if [ -z "$(_conn "$_k" "$_f" 2)$(_conn "$_k" "$_f" 3)" ]; then
            echo "deploy/$REGISTRY_RELEASE-staff-portal-api has no $_k database setting *_$_f" >&2
            exit 1
        fi
    done
done
MD_DB=$(_conn md DBNAME 2)
REGISTRY_DB=$(_conn registry DBNAME 2)
echo "=== $NAMESPACE: master data = $(_conn md USERNAME 2)@$(_conn md HOSTNAME 2)/$MD_DB, registry = $(_conn registry USERNAME 2)@$(_conn registry HOSTNAME 2)/$REGISTRY_DB (from deploy/$REGISTRY_RELEASE-staff-portal-api) ==="
_start_helper

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
# built before the 1.1.0 models has no display_name, pcode, ... columns, which
# the seed writes.
#
# Each ALTER only runs when its column is really missing (checked through
# pg_attribute, which does not depend on privileges). ALTER TABLE needs table
# ownership and an ACCESS EXCLUSIVE lock even when IF NOT EXISTS makes it a
# no-op, so where every column is already there -- dev, and staging's newer
# master-data build -- this takes no locks and needs no ownership.
schema_topup() {
    sed -E -e '/^BEGIN;/d' -e '/^COMMIT;/d' \
        -e "s/^ALTER TABLE IF EXISTS public\.([a-z0-9_]+) ADD COLUMN IF NOT EXISTS \"([a-z0-9_]+)\" (.*);\$/DO \$\$ BEGIN IF to_regclass('public.\1') IS NOT NULL AND NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = to_regclass('public.\1') AND attname = '\2' AND NOT attisdropped) THEN ALTER TABLE public.\1 ADD COLUMN \"\2\" \3; END IF; END \$\$;/" \
        "$HERE/master-data-schema-topup.sql"
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

# Read-only readings of master data and the registry, one pod each.
readings() {
    echo "=== readings ($1): $MD_DB ==="
    { cat "$GEO/mds-readings.sql"
      echo "BEGIN;"; cat "$GEO/kamuntu-scan.sql"
      echo "SELECT 'kamuntu', table_name || '.' || column_name, n FROM _kamuntu_hits ORDER BY 2;"
      echo "ROLLBACK;"; } | pg md
    echo "=== readings ($1): $REGISTRY_DB ==="
    { cat "$GEO/registry-readings.sql"
      echo "BEGIN;"; cat "$GEO/kamuntu-scan.sql"
      echo "SELECT 'kamuntu', table_name || '.' || column_name, n FROM _kamuntu_hits ORDER BY 2;"
      echo "ROLLBACK;"; } | pg registry
}
