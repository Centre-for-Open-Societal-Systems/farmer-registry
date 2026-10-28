# Dev delivery

The `Gen2-Package/farmer-registry/develop` Jenkins job delivers the Farmer
registry to the dev environment (namespace `farmer`, release `farmer-registry`). Crop,
Livestock, Commons, the connector and the dashboard releases are separate.
Staging is outside this document.

Every build validates the source, builds the six images and, on `develop`,
publishes them to ECR under the checked-out commit tag. What happens next is the
`DELIVERY_ACTION` parameter (trigger a deploy with
`buildWithParameters?DELIVERY_ACTION=deploy`):

| Action | Effect |
| --- | --- |
| `publish-only` (default) | Images published; the live release is untouched. |
| `deploy` | `ci/deploy/deploy-dev.sh` upgrades the existing release with this build's images and the chart pinned in `ci/deploy/oan-chart.json`. Values come from the live release; private values stay out of artifacts. |
| `fresh-install` | `ci/deploy/fresh-install-dev.sh` rebuilds the dev environment from an empty database. |

The chart is published by [COSS oan-helm](https://github.com/Centre-for-Open-Societal-Systems/oan-helm);
`oan-chart.json` pins its version and SHA-256, and `deploy-rc.sh` refuses any
other archive. Changing the pin is a reviewed commit.

## Fresh install

The dev environment is a development environment: its registry database may be rebuilt
whenever the metadata, schema or seed changes in a way an upgrade cannot carry.
`fresh-install` is the standard OpenG2P first install of the pinned chart, done
again, through Jenkins, and in this order:

1. Read the live release (values, manifest) and prepare the install values with
   this build's images, exactly as `deploy` would.
2. Archive `farmer_registry` and `farmer_registry_idgen` from a Job in the
   `farmer` namespace (the Jenkins account cannot reach Commons pods; the
   namespace holds a copy of the Commons PostgreSQL Secret). Each archive is
   listed with `pg_restore`, copied out, and streamed to the dev box into
   `/var/backups/oan/farmer/<stamp>-<database>.dump` over the
   `farmer-new-dev-backup-ssh` key. The remote checksum must match before
   anything is removed.
3. `helm uninstall` the release. Secrets the chart marks `resource-policy: keep`
   (database passwords, Keycloak client secrets, the AWE callback HMAC) remain.
4. `DROP DATABASE ... WITH (FORCE)` for both databases.
5. `helm install` the pinned chart with the prepared values. postgres-init
   recreates the databases and re-syncs the roles to the kept Secrets, the
   applications migrate the empty schema on start, the post-install hooks run
   the OAN seed (which now fails the job if the forms are wrong; see
   `oan-extension/src/oan_farmer_registry_extension/meta_data/90_checks.sql`)
   and the sanity smoke tests.

Everything registered on dev (farmers, households, documents, approvals,
issued IDs) is gone after step 4; the archive from step 2 is the only copy.
Commons services, the connector queue and the dashboard releases are untouched;
the reporting views are recreated by the chart.

To restore an archive instead, use the deployment credentials:
`pg_restore -d farmer_registry <stamp>-farmer_registry.dump` into an empty
database created by postgres-init, then `deploy` once so the hooks re-run.

## Why the seed is also a gate

The farmer seed upserts metadata and never deletes. A database that lived
through earlier seeds keeps rows no current seed writes, and on 27 October 2026
the dev environment showed the intake sections twice for that reason. The OAN layer now
attaches its sections by the upstream row's id (not by section), removes the
known leftovers by explicit id (`22_retired_rows.sql`), and `90_checks.sql`
fails the seed job on any section attached twice or any unexpected form or tab.
