# ODK form and intake

Form assets remain under odk/: the XLSForm, location media, ingestion transform,
and legacy setup assets. The published live form is farmer_profile; its permanent
connector configuration is private.

The canonical dev ODK Central is [odk-central-development.oanstaging.com](https://odk-central-development.oanstaging.com), with Farmer project `1`, Crop project `2` and migrated Livestock project `6`. See [hostname migration and archived old projects](../operations/odk-dev-hostname.md). The former Commons hostname remains a compatibility alias. Public staging remains the separate `odk-central.oanstaging.com` VM.

```sh
python odk/build_location_media.py --check
python -m pytest test/unit/test_odk_location_media.py test/unit/test_odk_geo_compatibility.py -q
python test/unit/test_odk_transform.py
```

Dev uses the active signed replacement described in the
[connector guide](../operations/connector.md). Staging retains its legacy connector
and separate database. Legacy plain manifests and setup SQL are not live upgrade
instructions.

ODK collector identity, farmer data and attachments persist through intake. Signed
dev ingestion, duplicate prevention and live AWE approval were accepted. The
geography report records the earlier catalog
migration; its pending-ingestion statements predate final acceptance.

Explicit live checks (the sanity suite) reside in test/sanity/. They create data and are
excluded from default test discovery. Performance workloads are also explicit,
mutating operations.

Cleanup exports and removes only verified synthetic rollout projects/forms and
accounts through supported Central operations. Keep the real Farmer project,
form, submissions, media, service account and permanent partner. Staging cleanup must preserve the real project and submissions.

## Every choice list from Master Data

`odk/tools/build_mds_form.py` builds the form whose dropdowns are Master Data's:

```sh
python odk/tools/build_mds_form.py --pack <openg2p-data>/packs/ETH-OAN   --geography <export of the target environment's Master Data geography>
```

It takes the v3 form and replaces the rows of every choice list that is a
Master Data list (gender, language, farming type, marital status, education,
income sources, crops, cluster role, land ownership, crop season, water
sources, livestock type, machinery, finance access, identity document type,
relationship to the head) with the pack's codes and displays, keeping the
Amharic and Afaan Oromoo wording of the choices the old form had. The
region, zone, woreda and kebele lists become external CSVs
(`odk/media/mds/*.csv`: `name` and `code` are the `level_value_id` Master Data
serves, `parent` the parent's), so a submission carries the location ids the
web intake stores and `odk/transform.py` passes every code through unchanged.

Geography belongs to each environment's Master Data, not to the pack. Since the
commons deploy of 28 October 2026 the dev environment serves the pack's plain
P-codes (`ET01` … `ET01010101`, 14 regions, 125 zones, 1362 woredas, 19535
kebeles), so the committed CSVs are the pack's geography; the catalogue migrated
on 27 October (`region-ET01` …, 1379 woredas) is gone. `--geography` takes a directory
holding `levels.json` and `values.json` in the pack's format, read from the
environment's `g2p_geo_levels` and `g2p_geo_level_values` (current rows);
without it the pack's own geography is used. Rebuild the CSVs for each
environment the form is published to. The chart's `odkGeoSync` (Central Entity
Lists kept equal to Master Data) replaces this step once a Central
project-manager login is provisioned for it. Yes/no answers and consent stay as they are.
The cooperative and union names are not Master Data lists, but they are filtered by the
region the farmer picked, which is now a Master Data code: the build re-keys them from the
v3 region number (1, 3, 4, 8) to the region code (ET01, ET03, ET04, ET08) by matching the v3
region's name to the geography's, writes `odk/media/PrimaryCoopList.csv` from the v3 list kept
in `odk/legacy-geo/PrimaryCoopList.legacy.csv`, and refuses to build if any cooperative or
union parent is not a region of the geography. A row whose region has no match is left out
and listed in the build report (none are, against the ETH-OAN pack). The animal, number of
animals and livestock water source questions are required for mixed farmers as well as
livestock farmers, for the farmer and for household members. Output:
`odk/ATI_Farmers_Profile_ODK_Form_v4.xlsx`, version `2026.10.31.1`;
`test/unit/test_odk_mds_form.py` checks the build against a small pack and
`farmer-extension/tests/test_odk_mds_codes.py` the transform's pass-through.

Publish it as a new version of the same `farmer_profile` form (project 1 on
the dev environment) together with the four geography CSVs and `PrimaryCoopList.csv` as form attachments; the connector and
the registry need no change. Choices the old form offered that Master Data
does not have (three crops, six machinery names) are not carried: the
registry's Master Data validation would refuse them anyway.

The 16 October staging location update
published form 1.0.5 with canonical cascading dropdowns, compact CSV media and
manual map placement. This form update is independent of the blocked Registry
upgrade; its shared-geography and partner prerequisites remain outstanding.


The dev location update published the
same form version 1.0.5 to `https://odk.commons-dev.oanstaging.com`, preserving
both existing submissions and their attachments. Registry delivery changes
land in develop before develop is promoted to staging.
