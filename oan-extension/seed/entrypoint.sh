#!/bin/sh
# The farmer seed, with its sample people taken from Master Data (the country
# pack's samples) instead of the Kamuntu demo files. Everything else is the
# farmer seed's own entrypoint, unchanged. OAN_SAMPLES_FROM_MASTER_DATA=false
# keeps the farmer seed's own people.
set -e

# Registry metadata is extension-owned configuration. Resolve the one known
# legacy UUID/mnemonic collision before the unmodified native metadata batch.
psql -X -v ON_ERROR_STOP=1 -f /oan/metadata_compat.sql

if [ "${LOAD_SAMPLE_DATA:-false}" = "true" ] && [ "${OAN_SAMPLES_FROM_MASTER_DATA:-true}" = "true" ]; then
  if python3 /oan/samples_from_master_data.py /tmp/oan-samples; then
    export OPENG2P_DATA_DIR=/tmp/oan-samples
  fi
fi

/seed/entrypoint.sh "$@"

# The farmer seed applies every file with ON_ERROR_STOP=0, so a failed check in
# 90_checks.sql is only a line in its log. Run the checks once more and let them
# fail the job: a seed that leaves the forms wrong must not count as complete.
echo "[oan-seed] Verifying the OAN metadata layer ..."
PGHOST="${REGISTRY_PGHOST:-$PGHOST}" PGPORT="${REGISTRY_PGPORT:-${PGPORT:-5432}}" \
PGDATABASE="${REGISTRY_PGDATABASE:-$PGDATABASE}" PGUSER="${REGISTRY_PGUSER:-$PGUSER}" \
PGPASSWORD="${REGISTRY_PGPASSWORD:-$PGPASSWORD}" \
  psql -X -q -v ON_ERROR_STOP=1 -f /seed/meta_data/zz-oan/90_checks.sql
echo "[oan-seed] OAN metadata layer verified."
