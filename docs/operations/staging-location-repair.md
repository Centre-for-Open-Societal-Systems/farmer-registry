# Staging locations and official OpenG2P samples

Farmer's pinned rc.544 Master Data client omitted the CSRF double-submit header
and cookie. Its credential reference also pointed to an optional Commons Secret
absent from namespace `far`. Requests failed with HTTP 403, leaving flattened
location names empty. Use Farmer's existing service client and its required local
Secret in both environments. Keep authentication and CSRF verification enabled.

The compatibility patch in `docker/common/patch_master_data_csrf.py` applies to
staff, partner and worker images. It preserves the token refresh, cache and
timeouts, adds CSRF to the initial request and retry, and fails the build if the
upstream client layout changes. Deployment guards allow only the checked-in
credential bindings; unrelated Secrets, routes, storage and database settings
remain protected. Promote the fix through feature → develop → staging, retaining
the rehearsal gate and `DEPLOY_STAGING=false` default.

## Official samples

The requested dataset is the official OpenG2P Ethiopian pack shipped in the
accepted db-seed image: **21 individuals and 6 households**. It is not 27 farmers.
The operator loader `docker/db-seed/import_official_eth_samples.py` validates the
complete files against a recorded SHA-256 and preserves their source IDs and GPS
coordinates. Records are labelled “OpenG2P sample” and marked
`created_by=openg2p-eth-samples-v1`, with deterministic internal IDs.

The pack uses OCHA Woreda codes, whereas live COSS geography is Region → Zone →
Woreda → Kebele. As explicitly agreed, sample catalog IDs and Kebele remain
unassigned. No IDs are padded, inferred or invented, and the shared catalog is
unchanged. The source's free-text Kebele is not imported as a canonical ID.

Use protected libpq `PG*` variables for the Farmer application role, after a
fresh checksum-verified backup and restored-database rehearsal:

```sh
python /seed/import_official_eth_samples.py --environment staging --namespace far
python /seed/import_official_eth_samples.py --environment staging --namespace far --apply
```

This operator workflow is separate from the required metadata deployment seed.
Keep `LOAD_SAMPLE_DATA`, `LOAD_GEO_DATA` and `LOAD_IMAGES` false in deployment
Jobs. The old CSV contains 500 Kamuntu people and must not be loaded here.

All 27 records commit together; failures roll back both tables. A rerun checks
the existing official samples and adds nothing. Modified sample sets or ID
collisions fail without overwriting existing records. The application role can
write only its Registry database; the script also rejects a database other than
`farmer_registry_far`, unless `--rehearsal` explicitly selects an isolated
`farmer_seed_rehearsal_*` database.

## Existing location projections

Export the live catalog using the authenticated Master Data APIs
`/geo/get_all_geo_levels` and `/geo/get_geo_level_values` for each level. Use the
standard request envelope, service bearer token and matching `X-CSRF-Token`
header/cookie. The repair verifies every ID, label, parent and level against the
checked-in canonical geo_seed fingerprint.

```sh
python scripts/operations/staging/repair_location_projections.py \
  --environment staging --namespace far --catalog /protected/live-catalog.json
python scripts/operations/staging/repair_location_projections.py \
  --environment staging --namespace far --catalog /protected/live-catalog.json \
  --apply --audit /protected/new-location-repair-audit.json
```

The repair changes only hierarchy JSON, four display names and the Woreda
projection. It preserves selected Kebele IDs, GPS, personal fields, approvals,
documents and existing history. A new protected audit file records before/after
values and is never overwritten. Unknown location IDs or non-Ethiopian country
values stop the operation. Samples with unassigned catalog IDs are skipped.

## Verification and recovery

```sh
python -m pytest tests/unit/test_location_projections.py tests/unit/test_master_data_credentials.py -q
# Against a restored database with protected PG* configuration:
FARMER_LOCATION_TEST_CATALOG=/protected/live-catalog.json \
  python -m unittest discover -s tests/runtime -p test_official_eth_samples.py -v
# Start locally; stop this simulation after verification:
postman simulation run postman/simulations/master-data-csrf.sim.yaml --port 4923 --output ndjson
# Separate terminal with the patched platform runtime:
MDS_SIM_URL=http://127.0.0.1:4923/mds \
  python -m unittest discover -s tests/runtime -p master_data_csrf_simulation.py -v
```

The Postman mock follows the measured installed API contract; it covers actual
client HTTP calls, hierarchy retrieval, cache reuse, 401 refresh, denied reads and
invalid credentials. Separately verify live reads and the full browser cascade.
Confirm official sample counts, existing Farmer preservation, no duplicate IDs,
normal register listing and unchanged connector idempotency keys.

Protect database dumps, source exports and repair audits; never publish them as
CI artifacts. For recovery, reconcile later writes and dependencies before
removing samples or reversing audited projections. Do not restore the entire
database over later real submissions. Helm rollback does not reverse data.
