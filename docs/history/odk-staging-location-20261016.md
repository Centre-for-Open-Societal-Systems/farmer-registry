# Farmer staging ODK location update ? 16 October 2026

Project `1`, form `farmer_profile` at `https://odk-central.oanstaging.com` now
publishes version **1.0.5**. Version 1.0.1 and the existing real submission remain;
the submission XML was compared byte for byte after publication. No acceptance
submission was sent and no real record was approved.

## Form changes

- Region ? Zone ? Woreda ? Kebele use cascading dropdowns for the farmer and
  household-member questions. Kebele previously used `minimal autocomplete`.
- Location uses `placement-map`, enabling manual map placement in Collect as
  well as browser map selection. GPS detection remains available.
- `odk/build_location_media.py` generates every real place from the checked-in
  `ethiopia_geo_seed.sql.gz`: 14 regions, 125 zones, 1,379 woredas and 19,535
  kebeles. Codes, canonical display names and parent relationships are verified.
  Existing explicit Other answers retain their prior intake policy.
- Zone and Woreda use external CSV lists; unused inline lists were removed
  because pyxform emits them even when the questions no longer reference them.
  Kebele media carries only the three columns used by the itemset. Publish the
  XLSForm and all four media files together, including PrimaryCoopList.csv.

## Verification

The production Central pyxform version is 3.1.0. Conversion and ODK Validate
passed locally with the same pyxform version. Central's warnings concern existing
missing translated media/default-language columns; these were reviewed before
uploading the draft with `ignoreWarnings=true`.

Authenticated Enketo browser checks exercised the largest Kebele branch (79
choices), compared all choices in that branch to canonical CSV data, changed
Region to verify stale child selections clear, and verified map clicks persist
coordinates. Desktop and 390-pixel mobile checks passed without JavaScript errors
or failed map-tile requests. A controlled geolocation callback verified the GPS
widget; a permission-denied callback verified manual placement still works.
Physical-device GPS and native Android Collect were not available for testing.
The headless browser's native geolocation callback timed out despite permission;
this does not establish a server-side GPS failure.

Measured synchronous Woreda-change work: 293.6 ms on published 1.0.1, 180.8 ms
on the draft, and 151.1 ms on published 1.0.5. These are individual browser
measurements, not a load test or a mobile-device performance guarantee. Initial
form readiness stayed around 2.5?2.8 seconds. Compiled XML decreased from
779,777 bytes / 21,143 elements to 403,506 bytes / 6,784 elements.

The existing draft was byte-identical to the published form and its media before
replacement. Protected backups include the XLSForm, XML, draft, media, version
history, submission XML, attachment/version metadata and submission media. All
21 file checksums were verified on the staging host at
`/var/backups/farmer-staging-20261016-odk-v2/`; a second archive remains in the
operator's protected workspace. The draft was published through Central's API;
no direct ODK database edits were made. Collect clients must get the new blank
form; browser users should reload the form.

## Registry cutover blocker

Read-only inspection of staging Master Data found all 21,053 canonical IDs, but
2,489 rows differ from canonical data: 289 parent relationships and 2,201 display
names (one row differs in both). Some parents contain display names rather than
IDs. The exact compatibility guard correctly refuses this snapshot.

All 18 Farmer tables exposing `geo_lowest_level_value_id` were surveyed. There
are 2,191 nonempty references across eight tables: four exact references and
2,187 references without a canonical target. Their mapping cannot be inferred
safely from IDs alone. The protected snapshot retains the reference groups.
No shared catalog or existing Farmer geography was changed. Restoring shared
catalog consistency and reconciling those records requires a separately reviewed
consumer inventory and migration; the Farmer-only rollout cannot meet its exact
geography acceptance requirement until that is resolved.

Partner inspection also found no `farmer-partner` registration or public keys in
staging Partner Management. The legacy connector has 398 failed runs reporting
`[SYS-ERR-001] UNEXPECTED_ERROR` and zero successful idempotency keys. Missing
partner registration is an unmet prerequisite; the generic error alone does not
prove it is the only cause. The replacement must remain disabled until partner
onboarding, key registration and signed end-to-end acceptance pass.

The Commons Services failed release describes an attempted change to an immutable
Master Data Deployment selector. Current Commons workloads are ready. No broader
Commons upgrade or recovery was attempted.
