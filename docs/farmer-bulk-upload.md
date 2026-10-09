# Farmer bulk upload

On the farmer intake list, choose **New Intake → Import from file →
Bulk upload farmers (CSV / XLSX)**, download a CSV or
XLSX template, replace its example row, select the intake form, and import.
Files are limited to 10 MB and 1,000 non-empty rows. XLSX uses the `Data` sheet
when present, otherwise its first sheet. Dates use YYYY-MM-DD; Ethiopian dates
must be text, including month 13. Phone numbers and national IDs should remain
text cells to preserve leading zeroes and long identifiers. Use lookup codes
configured in your deployment for crops, seasons and water sources.

Each valid row creates a new intake submission and enters normal approval.
The submission source is `STAFF_PORTAL` (the platform's supported source),
and the farmer's `import_source` is `IMPORT_FILE`.
It does not directly create or overwrite an approved registry record. Related
records are linked to the new farmer; supplied household members create a new
household parent in the same submission. Normal approval and deduplication
remain responsible for handling existing people. Uploading the same rows again
creates new submissions; this is not an upsert or an idempotent import API.

Results include source row numbers, submission links and per-row errors. The
error-report CSV contains row numbers and messages, not a re-importable data
file. Correct and upload only failed rows from the original spreadsheet. After
a lost connection or unexpected persistence/workflow failure, inspect intake
submissions before retrying; an external workflow might have accepted a request
even if the response or database commit subsequently failed. No automatic retry
is performed.

## API and deployment

- `GET /farmer/bulk-import/forms` lists farmer intake forms.
- `POST /farmer/bulk-import` takes multipart `file` and `form_id`. The standard
  G2P response payload contains `total`, `successful`, `failed`, and `results`;
  each result has `row`, `ok`, and either `submission_id` or `errors`.
- Routes inherit the union of the installed intake-save and finalize permissions,
  retain platform CSRF checks, and require an authenticated subject even when
  local middleware is disabled. Actor identity comes from the session.
- The staff UI uses its existing multipart document-upload route with a
  `farmer_bulk_import` query parameter. A server-only relay forwards cookies,
  authorization and CSRF to `BACKEND_API_URL`, including refreshed cookies back
  to the browser. Ordinary document uploads retain their original handler.
- Build the root Dockerfile's `staff-api`, `staff-ui`, and `db-seed` targets.
  Run the existing metadata seed to add the household-information section to
  the farmer intake form. The UI build fails if the pinned Next.js upload-route
  structure no longer matches the integration patch.

## Verification

```text
python -m unittest discover -s farmer-extension/tests -p "test_bulk_import*.py"
node --test --test-isolation=none test/staff-ui/test-bulk-proxy.cjs test/staff-ui/test-bulk-ui.cjs test/staff-ui/test-bulk-patch.cjs
```

Python checks require openpyxl, FastAPI, python-multipart, and httpx. The parser
tests are real CSV/XLSX round trips; controller/service tests mock platform and
database boundaries. JavaScript tests exercise the shipped proxy/browser code
and patch against fixtures. The existing `test/staff-ui/intake-rules.test.js`
suite (requires jsdom) also checks that document validation leaves the
spreadsheet picker alone. These tests run in the Checks workflow.

`test/bulk-import-integration.py` runs in the built staff API image against a
disposable copy of a seeded registry database. Set `BULK_TEST_DATABASE` and
`REGISTRY_STAFF_PORTAL_API_DB_DBNAME` to the same `farmer_bulk_test_*` database
and set `REGISTRY_STAFF_PORTAL_API_AWE_ENABLED=false`. Mount this repository
at `/tests` and run `python /tests/test/bulk-import-integration.py` using the
deployment's normal database/network settings. It writes synthetic submissions,
verifications and approved records, so never point it at a working database.

Verified locally against the pinned API (`0.0.0-develop.384`) and UI (`1.2.1`):

- Both Docker builds and bundle patch assertions passed.
- 25 bulk Python tests, 7 bulk JavaScript tests, 14 intake UI tests, the 22
  existing CI guard tests (plus 6 subtests), and the ODK transform check passed.
- Authenticated Chrome CSV and XLSX uploads passed through the real UI proxy
  into an isolated PostgreSQL copy. The import menu opens the dialog without
  adding a button above the portal header or causing hydration errors.
- Full CSV/XLSX examples persisted all supplied fields, rejected invalid IDs
  with row-specific errors, and rolled back failed rows. Required verifications,
  approval and ingestion passed, with farmer/household/child links preserved.

The database/browser checks disabled external AWE calls; they do not certify
a deployment's AWE policy, callback configuration or workflow service.

Before production rollout, verify restricted/expired sessions and CSRF with
the deployment's IAM configuration, actual external AWE approval/callbacks,
and ordinary document uploads. The 1,000-row parser boundary is tested; load-test
the maximum batch with production proxy timeouts because rows and workflow
service calls are processed sequentially.
