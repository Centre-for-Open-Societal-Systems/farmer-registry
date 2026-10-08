# Farmer bulk upload

On the farmer intake list, choose **Bulk upload farmers**, download a CSV or
XLSX template, replace its example row, select the intake form, and import.
Files are limited to 10 MB and 1,000 non-empty rows. XLSX uses the `Data` sheet
when present, otherwise its first sheet. Dates use YYYY-MM-DD; Ethiopian dates
must be text, including month 13. Phone numbers and national IDs should remain
text cells to preserve leading zeroes and long identifiers. Use lookup codes
configured in your deployment for crops, seasons and water sources.

Each valid row creates a new intake submission and enters normal approval.
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
and patch against fixtures. These checks do not prove compatibility with the
pinned platform images.

Before release, build the pinned images and verify authenticated CSV and XLSX
uploads, mixed results, 1,000 rows, forbidden/expired sessions, CSRF rejection,
intake readback of every section, and approval into the live registry with
correct parent links. Verify the ordinary document-upload route still works.
Check proxy/request timeouts with the maximum batch: rows are processed
sequentially, including approval-service calls.
