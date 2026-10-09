# Farmer Registry — ODK form

Field agents register farmers with the **Farmer Profiling Data Collection Form**
in ODK Collect (or the browser). ODK Central stores the submissions; the farmer
connector polls Central and posts each one to the registry, which turns it into
an intake for approval.

```
ODK Collect / web form → ODK Central → farmer connector (poll, photos inline)
  → partner API → celery: classify → farmer_transform.j2 → intake (PENDING, AWE approval)
```

## At a glance

| | |
| --- | --- |
| Form file | `ATI_Farmers_Profile_ODK_Form_v2.xlsx` |
| Form id / title | `farmer_profile` / "Farmer Profiling Data Collection Form" |
| Version | **1.0.4** in this file (location lists from the shared hierarchy). On ODK Central dev: 1.0.3 until 1.0.4 is published |
| ODK Central (dev) | `https://odk-central-development.oanstaging.com`, project **13** |
| Media | `media/KebeleList.csv` (19,535 kebeles), `media/PrimaryCoopList.csv` (cooperatives) |
| Location lists | generated from the shared hierarchy: `build_location_media.py` |
| Transform | `odk/templates/farmer_transform.j2` (uploaded to the MinIO `templates` bucket by db-seed) |
| Connector | `ci/connector/` (release `farmer-connector`, namespace `far`), pipeline data model `FARMER_ODK_MODEL`, partner `farmer-partner` |
| Languages | English (default), Amharic, Afaan Oromoo |

## What is where

| Path | |
| --- | --- |
| `docs/odk/ATI_Farmers_Profile_ODK_Form_v2.xlsx` | the XLSForm (survey, choices, settings) |
| `docs/odk/media/` | the CSVs the form reads (`select_one_from_file`) |
| `docs/odk/build_location_media.py` | rebuilds the location lists from the shared hierarchy |
| `docs/odk/FARMER_REGISTRY_ODK_COMPLETE_GUIDE.md`, `.html`, `.pdf` | the long-form guide (architecture, event table in 9.1) |
| `docs/odk/ODK_CONNECTOR_SERVICE_SETUP_GUIDE.md` | connector quick start |
| `odk/templates/farmer_transform.j2` | ODK submission → intake sections |
| `odk/test_transform.py` | renders the transform on an OData-shaped submission (CI) |
| `odk/setup_farmer_odk_connector.sql`, `odk/seed_connector_pipelines.sql` | the registry routing and a connector pipeline, for setting up by hand |
| `odk/test_odk_central_submission.py`, `odk/live_demo_submit.py` | send a test submission to Central |
| `test/test_odk_forms.py`, `test/test_odk_location_media.py` | form ↔ pipeline ↔ transform, location lists ↔ hierarchy (CI) |

## Form structure

| Group | Asks |
| --- | --- |
| `consent_form_section` | informed consent (three languages) |
| `household_questions` | household head?, registered?, relationship to head, member reference id |
| `national_id_section` | Fayda UID / RID, other ids |
| `basic_info` → `locale_info` | **region → zone → woreda → kebele** (cascading; "Other" woreda / kebele open a text field), language |
| `basic_info` → `personal_info` | names in English, Amharic, Afaan Oromoo; gender; birth date (Gregorian and Ethiopian); phones; email; farming type; disability; PSNP |
| `socio_economic_data` | marital status, education, income, family |
| `membership` | primary cooperative (`PrimaryCoopList.csv`, filtered by region), union, cluster, commodity, role |
| `farmer_photo_section` | **`farmer_photo`** (image) |
| `land_info` → `land_info_repeat` | per parcel: ownership, area, land id, **`land_certificate`** (image) |
| `crop_information` → `crop_repeat` | crop, date, water source |
| `livestock_info` → `livestock_repeat` | animal, count, water source |
| `agricultural_input`, `access_to_resource`, `access_to_finance` | inputs, machinery, finance |
| `other_farmers_in_hh` → `other_farmers_repeat` | other household members, each with their own location and **`hh_member_land_certificate`** (image) |
| `farmer_location` | GPS point |

## Location lists

Region, zone and woreda are choice lists inside the XLSForm (`choices_region`,
`choices_zone`, `choices_woreda`); the kebele comes from `media/KebeleList.csv`,
filtered by the woreda. All four are generated from
`docker/db-seed/seed-data/geo/geo_level_values.json`: the Ethiopia hierarchy
(14 regions, 125 zones, 1,379 woredas, 19,535 kebeles) that the registry's
Master Data is seeded with and that every registry's Master Data now shares. So
the form offers exactly the places Master Data knows, under the Master Data
name and parent.

Codes are the P-codes as numbers, as the form has always stored them:

| Level | Master Data id | Form value |
| --- | --- | --- |
| region | `region-ET04` | `4` |
| zone | `zone-ET0408` | `408` |
| woreda | `woreda-ET040801` | `40801` |
| kebele | `kebele-ET040801101001` | `40801101001` |

`farmer_transform.j2` pads the kebele back to `kebele-ET040801101001` and sends
it as `geo_lowest_level_value_id`; the farmer service fills region, zone,
woreda and kebele names from Master Data. A kebele picked as **Other** falls
back to the woreda (`woreda-ET040801`) with the typed name. The region number
also filters cooperatives (`PrimaryCoopList.csv`) and unions
(`choices_name_union`).

Region names keep their Amharic and Afaan Oromoo labels; the hierarchy has no
translations for zones, woredas and kebeles, so those show the Master Data name
in every language.

Version 1.0.4 moved the lists onto the hierarchy. Before it:

- 35 kebeles sat under three woredas Master Data does not have (`41602`,
  `42403`, `42701`), so picking one gave an intake with no location;
- the region, zone and woreda lists used an older numbering: 2 regions, 31
  zones and 258 woredas had codes Master Data does not use (Central Ethiopia
  was 10, now 7; Sidama 8 → 16; South Ethiopian 7 → 8; South West Ethiopia
  9 → 11; cooperatives and unions moved with their region), and 20 zones and
  454 woredas were not offered at all.

**When the hierarchy changes:**

```sh
python docs/odk/build_location_media.py          # rewrites the XLSX choice lists and media/KebeleList.csv
python docs/odk/build_location_media.py --check  # what CI runs (test/test_odk_location_media.py)
```

Then bump the version and publish (below). Needs `openpyxl`.

## Photos

`farmer_photo`, each parcel's `land_certificate` and a household member's
`hh_member_land_certificate` are image questions. ODK Central keeps the files;
OData gives only the file name. The connector downloads each submission's
attachments and sends them inline as `{"__type": "File", "name", "type",
"data": <base64>}` (`embed_attachments`, on by default; files over 10 MiB are
skipped and logged). The transform maps them to `record_image_document_id`
(Farmer Photo section) and `certificate_storage_id` (land, household member);
the celery worker uploads each to the documents bucket, attaches it to its
section (the intake header's **Attached Documents**), and approval carries it to
the farmer. A file that arrived as a name only is left out and logged
(`file_missing`).

## Field mapping

| ODK field | Registry | Notes |
| --- | --- | --- |
| `first_name_english` / `father_name_english` / `grandfather_name_english` | farmer `first_name` / `middle_name` / `last_name` | |
| `*_amharic`, `*_other` | `*_amh`, `*_om` | |
| `gender` | `gender` | `MALE` / `FEMALE` / `OTHERS` |
| `date_of_birth`, `date_of_birth_ec` | `birth_date`, `birth_date_ec` | |
| `household_head`, `is_psnp_user` | `is_household_head`, `is_psnp_user` | |
| `national_uid`, `national_rid` | farmer id documents (`UID`, `RID`) | spaces stripped |
| `primary_phone_number`, `secondary_phone_number` | farmer phones | normalised to 9 digits |
| `kebele` (or `woreda` with Other) | `geo_lowest_level_value_id` | names filled from Master Data |
| `location` | `enumerator_latitude` / `_longitude` / `_altitude` / `_accuracy` | GeoJSON from OData |
| `farmer_photo` | `record_image_document_id` | inline file |
| `land_info_repeat` | lands: `ownership_type`, `land_size`, `land_id`, `certificate_storage_id` | `TENANT` for rented |
| `crop_repeat` | crops: `commodity`, `season` (MEHER by default), dates | |
| `livestock_repeat` | livestock: type, head count | |
| `other_farmers_repeat` | household members, `certificate_storage_id` | |
| `__system.submitterName` | intake **Created By** (`<user> (ODK)`) | |

## Publishing a new version

The connector polls the form by id, so **keep the form id `farmer_profile`**;
change only the version.

1. Set the `version` cell in the settings sheet higher than any version Central
   has seen (Central refuses a repeat).
2. In ODK Central: project 13 → *Farmer Profiling Data Collection Form* →
   **Edit / Upload new definition** → this XLSX (accept the media-column
   warnings), then **Media Files**: upload `media/KebeleList.csv` and
   `media/PrimaryCoopList.csv`. Test the draft (Collect QR or the draft link),
   then **Publish**.

   Or with the API (an account that manages project 13):

   ```sh
   C=https://odk-central-development.oanstaging.com; P=13; F=farmer_profile
   T=$(curl -s $C/v1/sessions -H 'Content-Type: application/json' -d '{"email":"…","password":"…"}' | jq -r .token)
   curl -s -X POST "$C/v1/projects/$P/forms/$F/draft?ignoreWarnings=true" -H "Authorization: Bearer $T" \
     -H 'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' \
     -H "X-XlsForm-FormId-Fallback: $F" --data-binary @docs/odk/ATI_Farmers_Profile_ODK_Form_v2.xlsx
   for m in KebeleList.csv PrimaryCoopList.csv; do
     curl -s -X POST "$C/v1/projects/$P/forms/$F/draft/attachments/$m" -H "Authorization: Bearer $T" \
       -H 'Content-Type: text/csv' --data-binary @docs/odk/media/$m; done
   curl -s -X POST "$C/v1/projects/$P/forms/$F/draft/publish" -H "Authorization: Bearer $T"
   ```

3. Commit the XLSX (and any CSV) here. Collect picks up the new version on its
   next form update; submissions on older versions keep flowing.

## Connector

The `farmer-connector` release runs the connector service, worker, beat and UI
(`ci/connector/README.md`). Its pipeline for this form: base URL of ODK Central,
project 13, form `farmer_profile`, data model `FARMER_ODK_MODEL`, header
`partner-id: farmer-partner`, `resolve_nav_links` and `embed_attachments` on.
It polls about every minute for submissions newer than its watermark and
records each sent instance, so a submission is sent **once**:

- an **edit** in Central (same instance, new version) is not sent again;
- to re-send, make a new submission.

The registry side (data model, routing, template row) is seeded by db-seed
(`zz_farmer_odk_ingestion.sql`); the `farmer-partner` partner lives in Master
Data (`ci/connector/README.md`).

## Following a submission

The connector and the registry write JSON lines to `odk-ingest.jsonl` and
stdout (event table: guide, section 9.1):

```sh
kubectl -n far logs deploy/farmer-connector-worker | grep 'farmer_profile:uuid:<id>'
kubectl -n far logs deploy/farmer-registry-celery-worker | grep '"event"'
```

`attachments_summary` (listed / embedded / not uploaded / too large / failed),
`sent` or `send_failed`, then in the registry `submission_received`,
`file_stored` / `file_rejected`, and `ingest_succeeded`, `ingest_retry_scheduled`
or `ingest_failed` with the reason and what to do next.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Web form: "This form does not exist … (Attempted to access form with ID: )" | Enketo's link for the form was made under an older Central hostname. Regenerate the form's Enketo id on the Central server (DevOps). Collect is unaffected. |
| Submission never reaches the intake list | Connector log: `poll_failed`, `send_failed`? Registry log: `ingest_failed` (reason inside). An edited submission is not re-sent. |
| Photo / certificate missing | `attachments_summary` in the connector log: not uploaded on the device, over 10 MiB, or download failed; a connector older than the attachment change sends names only. |
| Location blank on the intake | The kebele (or woreda for Other) did not resolve in Master Data: check the lists are current (`build_location_media.py --check`) and the published version is the latest. |
| Created By shows `system` | Intakes from before the creator change, or a non-ODK partner. |
