# Farmer Location and livestock regression fixes

This change addresses G2R-333, G2R-334, G2R-361, G2R-362 and G2R-363. G2R-322
is a separate Livestock Registry task and is excluded.

## Findings and changes

| Issue | Finding and repair |
| --- | --- |
| G2R-333 | The effective Location schema already contains the geography widget. The pinned browser renders Region, Zone, Woreda and Kebele when Master Data reads succeed. Dev has an unqualified Master Data URL and an obsolete token endpoint; the dev routing overlay supplies the Commons service's qualified name and current realm URL. |
| G2R-361 | The pinned save service already normalizes coordinates to Float columns and preserves omitted fields. A disposable PostgreSQL test exercises Location save/read and a later Personal section save. The routing repair removes the stale dependency endpoints from the future dev deployment. |
| G2R-362 | The pinned browser displays the stored four-level hierarchy in read-only mode. Database checks preserve its names and hierarchy through later section saves. No duplicate Region/Zone widgets or columns are added. |
| G2R-363 | Latitude, longitude, primary language and local language exist in the effective schema and survive pinned save/read. Browser checks display the persisted values, including zero latitude. This report does not require a new field or a speculative renderer patch on latest develop. |
| G2R-334 | Blank livestock rows were accepted; count values were not normalized, and removed rows participated in duplicate checks. Active interactive rows now require type/count, validate an integer in the database range, and retain duplicate checks. Empty sections and incomplete legacy imports remain supported. |

No public endpoint, response envelope or field name changes. The existing
validation exception names the missing or invalid livestock field. Breed and
the remaining livestock attributes stay optional; a count of zero is valid.
No database NOT NULL constraint or existing-record cleanup is introduced.

The metadata repair updates only the type/count configuration, preserving
other table options and columns. It is safe to repeat. Base seed metadata has
the same required flags for new installations.

## Dev deployment behavior

The existing deployment helper merges `helm/environments/dev/registry-location.yaml`
over saved release values. It corrects Master Data API/token URLs for staff,
partner and worker plus the UI backend URL. Global defaults are overridden too.
Client IDs, client-secret references, identity providers and other service URLs
remain governed by their existing preservation checks.

The manifest guard permits only the exact reviewed routing changes and requires
them in all four rendered workloads. The staging path receives no routing overlay.
This change does not apply the broader optional Commons identity migration.

SSH work for this investigation was read-only: deployment metadata, selected
schema definitions, DNS checks and authenticated Master Data read operations.
The existing client authenticated against the current realm and the qualified
Master Data endpoint returned all four canonical geography levels. The installed
token endpoint failed to connect. Later probes also saw a transient DNS failure,
so these observations are not a continuous availability guarantee.

No dev deployment, live data write, Jira update or branch push was performed.
After deployment, repeat the five ticket scenarios through the full staff portal
with a new labelled synthetic application before closing the tickets. The local
checks below establish pinned component/service behavior, not a deployed portal
acceptance test or AWE approval.

## Repeatable verification

Offline metadata and deployment guards:

```powershell
py -m pytest -q -p no:cacheprovider tests/unit
```

Domain regressions using the pinned API package and current extension:

```powershell
docker run --rm --network none -v "${PWD}:/repo:ro" `
  -e PYTHONPATH=/repo/farmer-extension/src -w /repo/tests/runtime `
  --entrypoint python openg2p/openg2p-registry-staff-api:1.2.2-rc.544 `
  -m unittest extension.test_livestock_validation extension.test_farmer_geo_sync `
  extension.test_domain_validation_utils extension.test_add_farmer_qa_bugs
```

The explicit database check creates a disposable PostgreSQL on its own internal
Docker network, exposes no host ports, and removes its own resources afterward:

```powershell
& tests/integration/run-location-livestock.ps1
```

It runs the actual pinned intake save/read service, domain validation, ORM and
PostgreSQL. Master Data runs as a local HTTP fixture, with the real client making
HTTP requests. Checks cover hierarchy and coordinates/languages, later-section
preservation, atomic rejection of blank/mixed tables, zero count, an empty
livestock section and repeated metadata repair preserving unrelated configuration.

Browser checks use the actual public JavaScript from the pinned UI image.
Install Python Playwright and Firefox in the chosen test environment first.
Export public assets into an empty scratch directory outside the checkout:

```powershell
$env:FARMER_QA_UI_ASSETS = '<absolute scratch directory>'
docker run --rm --network none -v "${PWD}:/repo:ro" `
  -v "${env:FARMER_QA_UI_ASSETS}:/evidence" --entrypoint node `
  openg2p/openg2p-registry-staff-ui:1.2.2-rc.544 `
  /repo/tests/e2e/local/export_widget_assets.cjs
py tests/e2e/local/verify_location_widgets.py
```

The runner serves those copied assets and HTTP geography fixtures locally. It
checks cascading selection, Next's payload, read-only Location values, blank
and missing-count row errors, zero count, and cancellation. Exported module IDs
are deliberately tied to the pinned RC; update the harness when adopting a
different UI bundle. It does not bypass or test deployed authentication.

Postman CLI could not start because the device's managed Private Cloud manifest
was unreadable. No Postman workspace was created or published; the tests above
provide the local runtime/browser evidence instead.

## Local results, 2026-10-19

- Offline suite: 537 passed, 7 environment-dependent skips, 113 subtests passed.
- Selected domain/runtime suites: 84 passed. A separate run against the built
  API image's installed extension passed all 26 livestock/geography/coordinate checks.
- Browser runner with the pinned JavaScript and CSS: passed entry, Next,
  read-only visibility/value checks, row validation, zero count and cancellation.
- Disposable PostgreSQL and real-client/local-HTTP fixture check: passed,
  including repairing old metadata twice and preserving unrelated configuration.
- API image build: passed. Rendered chart: all four expected Master Data routes
  passed, with no duplicate environment entries, across 45 rendered documents.
- Python syntax, documentation links and `git diff --check`: passed.

The isolated branch starts at COSS develop `cc15ae18b66c`. Existing primary
checkout edits were preserved. These results do not establish that dev has
received the source changes.
