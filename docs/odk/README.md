# ODK form and intake

Form assets remain under odk/: the XLSForm, location media, ingestion transform,
and legacy setup assets. The published live form is farmer_profile; its permanent
connector configuration is private.

```sh
python odk/build_location_media.py --check
python -m pytest tests/unit/test_odk_location_media.py tests/unit/test_odk_geo_compatibility.py -q
python tests/unit/test_odk_transform.py
```

Dev uses the active signed replacement described in the
[connector guide](../operations/connector.md). Staging retains its legacy connector
and separate database. Legacy plain manifests and setup SQL are not live upgrade
instructions.

ODK collector identity, farmer data and attachments persist through intake. Signed
dev ingestion, duplicate prevention and live AWE approval were accepted. The
[geography report](../history/odk-geography-20261015.md) records the earlier catalog
migration; its pending-ingestion statements predate final acceptance.

Explicit live submission scripts reside in tests/e2e/. They create data and are
excluded from default test discovery. Performance workloads are also explicit,
mutating operations.

Cleanup exports and removes only verified synthetic rollout projects/forms and
accounts through supported Central operations. Keep the real Farmer project,
form, submissions, media, service account and permanent partner. Staging cleanup must preserve the real project and submissions.

The [16 October staging location update](../history/odk-staging-location-20261016.md)
published form 1.0.5 with canonical cascading dropdowns, compact CSV media and
manual map placement. This form update is independent of the blocked Registry
upgrade; its shared-geography and partner prerequisites remain outstanding.


The [dev location update](../history/odk-dev-location-20261016.md) published the
same form version 1.0.5 to `https://odk.commons-dev.oanstaging.com`, preserving
both existing submissions and their attachments. Registry delivery changes
land in develop before develop is promoted to staging.
