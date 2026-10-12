Registry-platform 1.2.2 upgrade
=============================

Existing Farmer databases need a coordinate-type migration before serving traffic
with the new images. The upstream G2PGeo/G2PGeoHistory models now declare latitude,
longitude and altitude as Float. Older Farmer tables retain varchar columns;
`create_migrate()` does not change their types. Intake save/read-back and register
queries then fail with `Unknown PG numeric type: 1043`, sometimes inside an HTTP
200 error response. Checking `/ping` alone does not validate this upgrade.

Run `scripts/migrate-rp-geo-columns.sh` with PostgreSQL 16 client tools and the
farmer database selected by `PGDATABASE`/`PGUSER`. Give it a new backup directory.
It backs up the database, validates the values, then converts the 36 legacy
coordinate columns in one transaction. Blank values become NULL; invalid
nonempty values abort the transaction. Dependent `fr_rpt_*` reporting views are
recreated from their dumped definitions, preserving owners, grants and indexes;
materialized views are refreshed in dependency order. Unexpected dependencies
abort instead of being dropped with CASCADE. Repeating the migration after
success is a no-op. Keep the generated backup and migration SQL.

For the local shared-infra setup, copy the script into
`openg2p-shared-postgres`, stop the farmer API/worker/beat containers, and run:

```sh
PGDATABASE=farmer_registry_db PGUSER=postgres \
  bash /tmp/migrate-rp-geo-columns.sh /tmp/farmer-geo-backup
```

Restart the API, worker and beat containers with the rebuilt images afterward so
their database connections do not retain prepared statements for the old types.
Do not reset volumes or rerun seed jobs.

The old intake-policy `def` to `async def` patch must also be removed: rc.544
already corrected every call site to call the synchronous helper. Keeping that
patch makes search and access checks pass a coroutine to SQLAlchemy.

Verification
------------

Run `test/verify_rc544_intake.py` inside the rebuilt staff-api image against a
disposable restored database selected by `REGISTRY_STAFF_PORTAL_API_DB_DBNAME`.
Its name must end in `_test`. It reads every domain model, saves and reads back
the Household section's No selection, searches submissions, and verifies that a
denying data policy excludes records. It creates a draft only in the test DB.
Use `--read-only` against the running database to check model reads, listing and
policy filtering without creating a draft. A seeded Farmer form is required.

Also run the platform patch/pin tests and the staff-UI bundle/upload checks.
Browser testing should cover the intake listing, Household save, existing
submission read-back, farmer search, and photo/certificate uploads.
