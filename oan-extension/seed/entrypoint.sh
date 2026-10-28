#!/bin/sh
# The native farmer seed entrypoint with an MDS-only sample consumer.
# No local CSV or synthetic-data fallback is supported.
set -e
if [ "${LOAD_SAMPLE_DATA:-false}" = "true" ] && [ "${OAN_SAMPLES_FROM_MASTER_DATA:-true}" != "true" ]; then
  echo "[oan-seed] Sample input must come from MDS; local fallback is no longer supported." >&2
  exit 1
fi
if [ "${LOAD_GEO_DATA:-false}" = "true" ]; then
  echo "[oan-seed] Geography is owned by the MDS country-pack loader, not Farmer." >&2
  exit 1
fi

# Registry metadata is extension-owned configuration. Resolve the one known
# legacy UUID/mnemonic collision before the unmodified native metadata batch.
psql -X -v ON_ERROR_STOP=1 -f /oan/metadata_compat.sql

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
