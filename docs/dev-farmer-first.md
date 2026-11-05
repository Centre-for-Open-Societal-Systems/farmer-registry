# Dev delivery

The `Gen2-Package/farmer-registry/develop` Jenkins job delivers the Farmer
registry to the dev environment (namespace `farmer`, release `farmer-registry`). Crop,
Livestock, Commons, the connector and the dashboard releases are separate.
Staging is outside this document.

Every build validates the source, builds the six images and, on `develop`,
publishes them to ECR under the checked-out commit tag. Then the same build
upgrades the existing dev release with them: there is no button for a normal
deploy. `DELIVERY_ACTION` stays only to choose the rare rebuild:

| Action | Effect |
| --- | --- |
| `deploy` (default) | `ci/deploy/deploy-dev.sh` upgrades the existing release with this build's images and the chart pinned in `ci/deploy/oan-chart.json`. Values come from the live release; private values stay out of artifacts. If the upgrade or its hooks fail, Helm puts the previous revision back (`--atomic`), the build fails, and the next build starts from the working release. A rollback restores the chart and values, not data that hooks wrote to a database. |
| `fresh-install` | `ci/deploy/fresh-install-dev.sh` rebuilds the dev environment from an empty database. Deliberate only. |

A branch-index build, or one started before this change, resolves an empty or
retired `publish-only` value to `deploy`. A release left in the `failed` state is
recovered by the next build without the automatic rollback (it would restore an
older revision over database changes the failed one already made).

The chart is published by [COSS oan-helm](https://github.com/Centre-for-Open-Societal-Systems/oan-helm);
`oan-chart.json` pins its version and SHA-256, and `deploy-rc.sh` refuses any
other archive. The pin moves in a reviewed pull request that the build opens
itself (next section).

## Chart pin updates

The last stage of a successful `deploy` build (`Propose chart pin update`) runs
`ci/deploy/propose_pin_pr.py`. It compares the pin with the newest Farmer chart on
the head of oan-helm `main`:

- same chart: "up to date", nothing happens;
- newer chart, same platform: it writes the new pin on a branch
  `bot/oan-chart-pin-<version>-<sha8>`, verifies the archive and runs the pin tests in
  the validation container, and opens a pull request to `develop`. Merging it is the
  deploy of the new chart; the PR text says what to read first;
- newer chart with another platform version: reported, nothing proposed (the images,
  `oan_compat.py` and the chart dependency must move with it; see
  `ci/deploy/bump_pin.py --help`);
- an older chart, or a different archive for the same version: refused.

It needs the Jenkins credential `oan-ci-app` (GitHub App, Contents and Pull requests
write on this repository). Without it the stage is UNSTABLE and the build still passes.
By hand: `python3 ci/deploy/bump_pin.py --latest` (dry run) or `<commit> --write`.
The staging pin (`oan-chart-staging.json`) is never touched by this stage.

## Chart publication

After the pin stage, the very last stage of a successful `deploy` build (`Publish chart`, `develop` only, never for a fresh
install or a pull request) runs `ci/deploy/package_chart.py`:

- the version comes from git: `0.0.0-develop.<commit count>`, using `scripts/ci/derive-version.sh` of oan-helm;
- the stage packages `helm/openg2p-farmer-registry`, with the tag `<commit12>@sha256:<digest>` of `staffUi`, `staffApi`,
  `partnerApi`, `celeryWorker`, `celeryBeat`, `dbSeed` and `sanity` written into the packaged copy only;
- it adds the archive to `repository/develop/` of oan-helm, where a workflow updates the index, changelog and rollback history.

Nothing is committed back here, and no pull request is needed. If publishing fails the stage is UNSTABLE and the build still
passes. See `docs/chart-channels.md` and `docs/rollback.md` in oan-helm.

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
   `farmer-extension/src/openg2p_registry_farmer_extension/meta_data/zz-oan/90_checks.sql`)
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
