> Historical evidence. Use [current operations](../operations/README.md) for maintenance; recorded commands and job links describe past rollouts.

> Historical server diagnosis and rollout prerequisites from PR #91. The repository now uses the upstream RC layout; old Jenkins/local-gen2 commands below are not the new deployment procedure. See [current adoption notes](coss-upstream-adoption.md).

# New Gen2 db-seed: read-only findings (2026-10-14)

Inspected the server behind `new-gen2-development`. No Jobs were rerun, no
resources were applied/deleted, and database queries used `BEGIN READ ONLY`
with `default_transaction_read_only=on`; all transactions were rolled back.
Only aggregate counts and schema/seed metadata were queried, not farmer PII.

## Deployment, not a namespace migration

The server already uses `farmer` for the registry and `commons` for shared
services. There is no `far` or `common` namespace. Shared Base is `2.3.3` and
Services is `2.3.4-rc.245`; those running releases are not upgraded by this PR.
The existing AWE and other shared-service aliases point into `commons` and are
not owned by the farmer Helm release. Reuse them; do not delete/recreate/adopt
them just to satisfy the former PR assumptions.

Farmer release revision 4 is `deployed` with wrapper chart `1.2.1-rc.182` and
ECR image tag `0ee17a2874fb`. The corresponding COSS commit's unified Dockerfile
pins registry-platform `0.0.0-develop.384`. It is NOT the unmerged PR's rc.544
build. Installed Python package versions alone are not proof of a base-image
tag; the image revision's build source is the evidence here.

## Why green does not mean the seed is correct

The latest Job `farmer/farmer-registry-db-seed` completed on
2026-10-13 at 10:35:43 UTC. Its main container exited 0. Nevertheless:

- Metadata seeding logged duplicate-primary-key SQL errors for `data_models`,
  `g2p_attributes`, themes/theme values, incoming patterns/key paths/templates,
  and outgoing templates. Execution continued and printed `meta-data completed`
  and `Done`. These SQL inserts are not rerunnable and their SQL failures did
  not propagate to the container exit status.
- `LOAD_SAMPLE_DATA=true`, `LOAD_IMAGES=true`, `SYNC_GEO_WIDGETS=false`.
  Master Data supplied 21 Ethiopian people and 6 households, but attached farmer
  fixtures still contain fictional Kamuntu locations. The log reports **0 geo
  resolutions and 1,018 slug-path fallbacks**. Read-only DB checks confirmed
  **all 509 land rows** contain `kamuntu/...` location IDs; they cannot match the
  1,271 Ethiopian geo values in Master Data.
- The upload step uploaded/catalogued **500** images but updated **0** farmer
  rows. The uploader derives legacy `i0001`-style IDs from image filenames;
  none of the 21 loaded farmer IDs match that format. DB checks confirmed
  **21 farmers, 0 image links**, plus 6 households, 757 crops and 504 document
  catalogue entries. Upload success is not successful record linkage.
- Sanity ran **smoke only**: 3 passed, 9 deselected. It did not validate these
  data relationships, AWE end-to-end, or photo display.

## Earlier failures

Helm revisions 1-3 failed (initial timeout, then db-seed `BackoffLimitExceeded`).
Their old seed pods/log directories are no longer present, so their exact
exceptions cannot be recovered from the surviving pod's logs.

The visible configuration change from revision 3 to successful revision 4 is
MinIO's endpoint: `minio.commons-dev.oanstaging.com` became
`minio-api.commons-dev.oanstaging.com`. Read-only HTTPS health probes confirmed
the former returns the HTML console page, while the latter returns the S3 API
health response with S3 headers. This strongly implicates the console/API mix-up
in earlier upload failures, but is not a substitute for the missing error logs.

## Code changes versus data repair

The dev profile is corrected to `farmer`/`commons`, preserves the API MinIO
hostname from live values, reuses existing aliases, and disables demo/image/bulk
seed loaders while retaining metadata/templates and geo-widget synchronization.
This prevents the next upgrade from repeating the mismatched demo-data load.
It does NOT repair existing land IDs, assign images to records, or make the
legacy SQL runner fail-fast. Those require a separately tested seed-hardening
change and an approved, backed-up data repair—not another blind seed rerun.

Before upgrading runtime images to rc.544, address the documented coordinate
type migration: the inspected farmer/land latitude, longitude and altitude
columns are still `varchar`. Rehearse on a restored database and validate
actual reads/save-readback; `/ping` does not check that compatibility.

The new `scripts/operations/commons/check_geo_schema.py` was also exercised in the existing staff
API pod read-only. It correctly rejected **24** incompatible coordinate columns
across Farmer, Household, Household Member, Land and their history tables, and
exited 1 without changing schema/data. The CI preflight uses this gate to stop
an existing deployment's rc.544 upgrade until the migration is complete.
