# New-dev ODK hostname and old-VM archive

Executed on 16 October 2026. Canonical Central is now
[odk-central-development.oanstaging.com](https://odk-central-development.oanstaging.com).
The user changed Route 53 from `13.207.43.8` to `13.201.58.55`, TTL 300.
Authoritative and application-side DNS returned the new address. Staging remains
on its separate VM at `odk-central.oanstaging.com`.

## Configuration and ownership

New dev remains `commons/commons-services-odk-central-*`, Central v2025.2.1.
Images, databases, storage and Secret references were retained. Only backend and
Enketo rolled for the configuration changes:

- Backend `DOMAIN` and derived `EMAIL_FROM` use the canonical hostname.
- Keycloak staff client `openg2p-odk` includes its canonical callbacks and origin,
  with existing callback/origin entries retained.
- Enketo's external login URL uses the canonical hostname. Its existing blank
  linked-server matcher is preserved for cached forms on the compatibility URL.
- Both installed Istio routes and the map Referrer-Policy correction remain.
  [odk.commons-dev.oanstaging.com](https://odk.commons-dev.oanstaging.com) is a
  compatibility alias serving the same installation, not another database.

At the next reviewed **Commons Services** deployment, combine
[`values-dev-hostname.yaml`](../../ci/odk/values-dev-hostname.yaml) with
[`values-map-tiles.yaml`](../../ci/odk/values-map-tiles.yaml). The overlay keeps
the Commons-managed route on the compatibility hostname; preserve the separately
installed canonical route recorded in
[`new-dev-canonical-route.yaml`](../../ci/odk/new-dev-canonical-route.yaml).
The Farmer pipeline does not apply these Commons files. Live targeted patches
do not update Helm's stored values; deploying Commons without the overlays can
revert them. Helm lint/render against installed ODK chart v2025.2.2 reproduced
live backend variables, Secret references, Enketo configuration and the map fix,
allowing equivalent API representations of empty environment values.

## Connectors and Livestock migration

All six existing new-dev definitions now use the canonical base URL. They were
paused and snapshotted before retargeting. IDs, mappings, sender settings,
failed-run history, successful idempotency rows and checkpoints were preserved.
Each registry retains one existing beat deployment with one replica.

| Connector | Project | Result |
| --- | --- | --- |
| Farmer | `1` | Form/OData reads passed; resumed successful polling |
| Crop Prep, Sown, Harvest | `2` | Form/OData reads passed; resumed successful polling |
| Crop Plan | `2` | URL updated; paused because version 1.0 remains an unpublished draft and form reads return 403 |
| Livestock | `6`, migrated from old `14` | Form/OData reads passed; polling resumed; existing partner failure remains below |

The user chose to migrate the connected Livestock project and archive the rest.
New project **6**, Gen2 Livestock Registry, contains `livestock_registry`, all
three available form versions and their media, plus eight current submissions.
Form XML, form media and all eight submission XMLs were verified byte for byte.
Each current submission had one version and no uploaded submission attachment;
review states remain unset. The old Livestock form was closed after a final
source-XML comparison; the new form is open. A dedicated reader has viewer
access only to project 6, with credentials installed through protected handling.

Supported REST imports assign new receipt timestamps and the migration actor.
Original timestamps, submitter identities, audits and deleted historical data
remain in the protected export and complete old-server database archive. These
are not presented as unchanged destination metadata. The temporary publisher
was deleted and its login was verified rejected. Permanent readers still work.

Livestock retains seven successful idempotency keys matching seven of the eight
source instances. The remaining instance already failed before migration with
**`PARTNER_NOT_REGISTERED`**. The first resumed poll retried it and returned
`PARTIAL`; subsequent empty polls returned `SUCCESS`. No successful key was
added or failure reclassified. Event keys use `form_id:instance_id`, preserving
deduplication across the project-ID change. Empty-poll success does not establish
that the eighth submission reached Registry: partner registration and a reviewed
retry remain separate work. No migrated record was approved.

Crop Plan's draft and seven media files are preserved. Publication is a separate
content decision; its connector stays paused pending that decision.

## Verification

- Canonical and compatibility HTTPS endpoints passed normal TLS verification
  and returned 200.
- Login reaches the staff-realm Keycloak login page with
  `redirect_uri=https://odk-central-development.oanstaging.com/v1/oidc/callback`.
  This verifies redirect acceptance, not a complete credential-based SSO login.
- Authenticated Chrome and Firefox rendered all visible map tiles with HTTP 200
  and canonical-origin Referer headers. Clicking saved a point. No synthetic
  submission was created.
- Canonical Region/Zone/Woreda/Kebele choices, including the largest 79-entry
  Kebele branch, passed. Parent changes cleared child selections. Controlled
  browser geolocation worked; physical-device GPS was not tested.
- Farmer version 1.0.5, both existing submission XMLs and published media were
  compared with the protected backup and preserved.
- Repeated automatic polls preserved Farmer/Livestock checkpoints and successful
  key counts (three and seven). Published Crop connectors have no submissions
  and no checkpoints to advance.

## Archive and recovery

The old VM remains running; it was not stopped or terminated. Its database had
**18 projects, 74 form rows and 207 submission rows**, including deleted history.
The complete dump and Compose/environment/backend configuration were archived
independently. No external S3 blob store was configured on that old backend;
the dump includes its stored blobs.

Protected locations:

- Old VM: `/var/backups/new-dev-odk-domain-20261016/`.
- New dev: `/var/backups/farmer-dev-odk-hostname-20261016/`, including the old
  archive, checksums, Livestock API export, pre-change Central/connector dumps,
  configuration and execution evidence.
- Operator: `Temp/farmer-staging-20261016-private/odk-hostname/`.

Old dump SHA-256:
`924a602a62fdf206f4abeefb725ab0a71b207b4680d0989aa1c2682b7d2aa9cd`.
Archive checksums passed. A full isolated PostgreSQL 16 restore verified all 18
projects, 74 forms, 207 submissions and eight current Livestock submissions.
Recovery does not depend on the old VM. Archives contain credentials and data;
never publish them in Git or Jenkins artifacts.

Before recovery, pause ingestion, take fresh snapshots and reconcile records and
checkpoints. A DNS rollback selects different old project IDs/data. Never restore
the old dump over live Farmer/Crop databases. Preserve new project 6 and use the
archive only in an isolated restore or a separately reviewed migration.

Source delivery stays feature → develop → staging. A merge does not deploy
Commons, publish Crop Plan, register the Livestock partner or approve records.
See [merge handoff](merge-develop-staging.md).
