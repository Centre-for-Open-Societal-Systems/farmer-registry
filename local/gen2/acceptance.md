# Local Gen2 acceptance

Tested on 2026-10-14 against preserved local Farmer data, published Commons
Services 2.3.4-rc.245 images, and Farmer images built from this branch. Upstream
DevOps PR #92 (`67d47a8`) is included. No server deployment was performed.

Final results: **13/13 live acceptance tests passed** (61.56 seconds), including
audit persistence; **73 regression tests plus 6 subtests**, **14 local topology
tests**, **12 domain-helper tests**, and the four-loop worker DB check passed.

## Reproduce registry checks

`sanity.env.example` contains local demo credentials only. Copy it to an ignored
file if overrides are needed. The suite provisions labelled test identities,
records and PM/CM bindings. It adds its test user to the change-request approval
policy while retaining existing approvers.

```sh
docker build -f docker/sanity-tests/Dockerfile -t farmer-gen2-local/sanity:dev .
docker run --rm --network openg2p-gen2 \
  --add-host keycloak.localtest.me:host-gateway \
  --env-file local/gen2/sanity.env.example \
  --entrypoint pytest farmer-gen2-local/sanity:dev \
  -v tests/test_smoke.py tests/test_e2e_negative.py tests/test_e2e_dci.py \
  tests/test_e2e_change_request.py tests/test_e2e_intake.py
```

Without an ODK instance ID or audit DB configuration, those checks explicitly
skip. For full coverage add `SANITY_ODK_INSTANCE_ID=uuid:<fresh-instance>` and
`SANITY_AUDIT_PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD` for the local audit DB.
Each ODK approval test needs a fresh submission; an already-approved record
must not silently satisfy a test of the approval path.

## ODK setup and fixture

Existing local `odk-central` and `odk-connector` Compose projects remain separate.
Central is `https://odk.localtest.me:8443`, project 1; the connector API is
`http://localhost:8150`, using `farmer_connector` and Redis DB 10.

The test uncovered stale local components, corrected explicitly:

- Published the repository XLSForm 1.0.4 and both media CSVs to local Central.
  The existing 1.0.1 form had no `farmer_photo_section` field.
- Rebuilt the connector from `openg2p-connector-service/`; the previous image
  sent filenames without embedding contents. The local worker uses two processes.
- Changed the existing pipeline's model from `FARMER_DATA_MODEL` to
  `FARMER_ODK_MODEL`, preserving its login and enabled state. Onboarded
  `farmer-partner` in shared PM through HTTP with a local test key; its legacy
  Master Data partner row is insufficient for rc.544.
- Updated only `templates/farmer_transform.j2` in local MinIO from this branch.
  No bulk/demo seed was run.

Submit a fresh `Genodktest` farmer through Central's OpenRosa endpoint
`/v1/projects/1/submission` with `X-OpenRosa-Version: 1.0` and multipart
`xml_submission_file`. Include a real image referenced by
`farmer_photo_section/farmer_photo`, a land certificate, location codes
`4/408/40801/40801101001`, and GPS `7.9 39.1 1800 5`. Assertions check:

- one registry message for `farmer_profile:uuid:<instance>`;
- completed ingestion, photo/certificate document links and submitter attribution;
- resolved geography, both AWE approval stages, and asynchronous register promotion;
- photo and geography retained on the approved register record.

## Bugs fixed during acceptance

1. The extension converted coordinates to strings after rc.544 changed the
   columns to Float. Numeric and string inputs now normalize to numbers.
2. Worker modules use different async loops but shared an asyncpg pool. Async
   sessions now use `NullPool`; synchronous pooling remains unchanged.
   `test/verify_celery_async_loops.py` checks four event loops against PostgreSQL.
3. The preserved document-history table lacked rc.544's `event_type` column,
   failing attachment promotion after approval. Applied the explicit SQL in
   `ci/gen2/migrations/document_history_event_type.sql` locally; the old history
   table was empty. The read-only startup/deployment gate now checks this column
   as well as coordinate types. The migration is never run automatically.

## Limits

DCI tests verify signatures and consent enforcement. The pinned legacy ODK
`/partner/ingest_data` path resolves an active PM partner but does not
cryptographically verify its envelope signature. This test does not establish
that guarantee; securing this legacy endpoint remains separate platform work.

Server coordinate migration, existing seed-data repair and seed repeatability
remain rollout work. Further restore work was excluded at the user's request.
Generated logs, local secrets and record data are ignored, not attached to the PR.
