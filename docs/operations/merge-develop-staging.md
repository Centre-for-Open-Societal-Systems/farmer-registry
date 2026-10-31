# Merge Farmer changes through develop into staging

Source moves **feature branch, then develop, then staging**. Merging source never changes the
staging cluster by itself.

## Merge sequence

1. Review and merge the feature PR into `develop`. Wait for the
   [Farmer Jenkins develop build](https://jenkins.oanstaging.com/job/Gen2-Package/job/farmer-registry/job/develop/).
   Develop builds and publishes the images and can deploy to the dev environment (namespace `farmer`, `DELIVERY_ACTION`).
   Confirm the dev release, login and normal Registry use before promoting that commit.
2. Open the [develop-to-staging comparison](https://github.com/Centre-for-Open-Societal-Systems/farmer-registry/compare/staging...develop).
   Create the promotion PR with base `staging` and head `develop`; the PR check rejects any other source branch.
   Wait for its checks, then merge it.
3. The [Farmer Jenkins staging build](https://jenkins.oanstaging.com/job/Gen2-Package/job/farmer-registry/job/staging/)
   validates with `DELIVERY_ACTION=validate-only`, `DEPLOY_STAGING=false` and `COORDINATE_SERVICES=false`
   by default; the build description says VALIDATION ONLY. A merge leaves the running staging release untouched.
4. Change staging only through [the staging procedure](staging-upgrade.md): `fresh-install` for the first OAN install
   in namespace `farmer`, `deploy` afterwards. Both need `DEPLOY_STAGING=true`, fresh protected evidence
   (`staging-farmer-rehearsal`) and, for `fresh-install`, the backup target credentials. Images are promoted by digest,
   not rebuilt.

## What the staging branch deploys

- The OAN chart `openg2p-farmer-registry` pinned in `ci/deploy/oan-chart-staging.json`, into namespace `farmer`,
  with values from the pinned oan-helm commit and the overlays in `helm/environments/staging/`.
- The legacy release in namespace `far` (`farmer_registry_far`, platform rc.544) is not deployed to, upgraded or
  removed by this pipeline.
- `ci/deploy/oan_chart.py require-deployable` accepts only `dev` and `staging`, and only with the pin made for the
  requested environment; the OAN renderer accepts the same two environments in namespace `farmer`.

## Before the first promotion

`staging` is far behind `develop`; the promotion PR carries all of it. After it merges, the first staging build is
validation only. The prerequisites for the install (Commons state, namespace Secrets, pinned values commit, backup
credentials, evidence) are listed in [the staging procedure](staging-upgrade.md).

## ODK target

Staging ODK Central runs inside Commons at `odk-central.oanstaging.com`, as on dev; the former separate VM is
retired and its form `farmer_profile` 1.0.5 is not migrated by this change. See [map configuration](odk-map-tiles.md).

## Verification for merge review

- `bash ci/validation/validate.sh`: unit tests, deploy and fresh-install shell tests (dev and staging), environment
  contracts `dev`, `staging`, `staging-legacy`, documentation links.
- GitHub checks on the PR head remain the merge gate.
