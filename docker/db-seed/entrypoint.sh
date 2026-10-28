#!/bin/sh
# The farmer seed's own entrypoint, unchanged, between OAN's metadata
# compatibility step and a strict re-run of OAN's metadata checks. With
# LOAD_SAMPLE_DATA=true it runs /seed/load_sample_data.py, which is OAN's loader
# (the country pack's sample people as Farmers; see load_sample_data.py).
set -e

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
