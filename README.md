# OAN Farmer Registry

The OAN extension adds Farmer, household, land, crop, livestock, membership and
identity workflows to the published OpenG2P Farmer 1.2 runtime. The candidate
uses platform **1.2.2-rc.557**. Forms use section schemas, registered widgets,
themes and language metadata; behavior uses registered extension services.
OpenG2P framework and worker sources remain unchanged.

This delivery branch composes the reviewed OAN source with the existing COSS
delivery tooling. **Promotion remains blocked.** Source checks and disposable
database rehearsals do not establish live acceptance. Read the
[candidate scope and remaining checks](docs/refactor-candidate.md) before using
historical operational instructions.

The layout follows the OpenG2P registry repositories (`OpenG2P/farmer-registry`):

| Path | Purpose |
| --- | --- |
| `farmer-extension/` | The Farmer extension, `openg2p_registry_farmer_extension`: OpenG2P's Farmer extension (`openg2p_farmer/`, unchanged) with the OAN models, services, metadata (`meta_data/zz-oan/`), ODK enrichment and reporting on top, with its tests |
| `sample-farmer-extension/` | OpenG2P's Farmer extension as published, for comparison on upgrades; never built |
| `ui/staff-ui/overrides/` | Registered OAN widgets and supported source overlays |
| `docker/<component>/Dockerfile` | Images built FROM the registry platform images with the Farmer extension installed: staff-api, partner-api, celery, staff-ui, db-seed, sanity-tests |
| `docker/db-seed/` | The seed image: the registry platform's db-seed with the Farmer extension's metadata, approval policy, templates, reporting views and sample loader |
| `helm/` | Environment overlays read by `ci/deploy`, plus the Farmer chart sources |
| `ci/`, `Jenkinsfile` | Jenkins delivery, source and native metadata checks |
| `integrations/` | Registry connector adapters |
| `odk/` | Source XLSForms, form builders and media |
| `test/` | `unit/` (offline, CI), `integration/` (shell harnesses, disposable DBs), `runtime/` (inside built images), `sanity/` (sanity-tests image) |
| `performance-testing/` | Load-test plan, Locust workloads, bulk seeding and report tools |
| `scripts/` | `bump-rp-version.sh`, `uninstall-registry.sh`, doc-link check and live operations tools |
| `docs/` | Current guides |

Sample data lives only in [openg2p-data](https://github.com/Centre-for-Open-Societal-Systems/openg2p-data).
The db-seed image's sample loader (`docker/db-seed/load_sample_data.py`, run only with
`LOAD_SAMPLE_DATA=true`) reads the sample people from Master Data's API and their farm facts
from the ETH-OAN pack. It enters each person as a farmer intake and approves it like any other:
stage 1 as `alex.carter`, stage 2 as `nina.patel`, signed in through the staff portal's sign-in
with the chart's sample-user password (`global.aweApproverUserPassword`); never the password grant,
never a Keycloak change. Besides the chart's intake-seed settings it needs `STAFF_IAM_URL` and the
`MDS_*` client settings on the db-seed Job. No environment enables it (`ci/deploy/deployment.py`
rejects `LOAD_SAMPLE_DATA`, `LOAD_GEO_DATA` and `LOAD_IMAGES`); New Dev already holds the 21 sample
farmers, entered and approved the same way.

Helm ownership is centralized in
[COSS oan-helm](https://github.com/Centre-for-Open-Societal-Systems/oan-helm).
The [deployment profile](ci/deploy/oan-chart.json) pins an immutable chart and
SHA-256 checksum. Dashboard UI/API and connector releases have independent
owners; this candidate does not replace their running releases.

The Fayda ID is typed on the intake form and approved like every other value;
the record is then verified with the platform's `id-authentication` widget and
core's registrant authentication (no OAN verification code). A typed value alone
does not establish verification. Offline ODK identity evidence remains
unverified until normal approval.

For delivery tests, install `ci/validation/requirements.txt` and run
`python -m pytest` (runs `test/unit`). Native extension and repeatable metadata checks
run against the published runtime in CI. See [the documentation index](docs/README.md),
[native ODK intake](docs/odk-native-intake.md) and
[dev delivery](docs/dev-farmer-first.md).

CI / CD Build

Following are the images which are created by the CI / CD pipeline from this repo
1. Celery image - pulled from the openg2p RP
2. DB seed image - created from openg2p-data repo
3. partner-api image - pulled from the openg2p RP
4. staff-api image
5. staff-ui image

Local acceptance runs serially: Commons + Farmer + Crop, then Commons + Farmer +
Livestock. Existing dev and staging deployments are unchanged by publication
of this candidate.
