#!/bin/sh
# Load the Ethiopia location hierarchy (region > zone > woreda > kebele) into a
# namespace's Master Data. See docs/commons-services-upgrade.md, "Location
# hierarchy".
#
#   KUBECONFIG=... NAMESPACE=far  DRY_RUN=true ci/commons-services/seed-locations.sh
#
# Source: docker/local-dev/geo-seed/ethiopia_geo_seed.sql.gz, ids <level>-<P-code>,
# parents linked by id. Additive only: existing locations keep their id and
# every column. Guards abort the whole transaction when the namespace holds a
# hierarchy this cannot sit next to -- the ETH pack in `far` (run
# migrate-far-geo.sh) or the livestock registry's name-keyed variant in `live`
# (its own db-seed owns that one; see docs/commons-services-upgrade.md).
#
# DRY_RUN defaults to true: the transaction runs, guards included, and rolls
# back. Readings are printed before and after either way.
#
# In `far` this refuses to run until migrate-far-geo.sh has moved the ETH-pack
# hierarchy aside; that script runs this step itself.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/geo-common.sh"

lint_seed
readings before

echo "=== seed locations into $NAMESPACE/$MD_DB (DRY_RUN=$DRY_RUN) ==="
{
    echo "BEGIN;"
    schema_topup
    cat "$GEO/seed-tables.sql"
    seed_rows
    cat "$GEO/seed-apply.sql"
    end_tx
} | pg "$MD_DB"

readings after
[ "$DRY_RUN" = "false" ] || echo "=== DRY RUN: rolled back, nothing was changed ==="
