# Release

How a Farmer Registry version is numbered, built and promoted. Where each version goes is in
[deployment](deployment.md).

## Versions

| What | Where it is set | Example |
| --- | --- | --- |
| Repository version | `version` in [`init.yaml`](../init.yaml) | `1.0.1` |
| Build version: image tag and chart version | `<version>-<branch>.<BUILD_NUMBER>` ([`ci/deploy/image_names.py`](../ci/deploy/image_names.py)) | `1.0.1-develop.57` |
| Staging version | the rc of a develop build, added by the staging promotion | |
| OpenG2P platform (`rpVersion`) | `ARG BASE_IMAGE_VERSION` in `docker/*/Dockerfile`, `Chart.yaml`, `Chart.lock` and the native contract | `1.2.2-rc.625` |
| Farmer extension package | `__version__` in `farmer-extension/src/openg2p_registry_oan_farmer_extension/__init__.py` | `1.0.3+oan.1` |

The six platform images carry `-<rpVersion>` in their repository name, so a platform bump starts new ECR repositories:
`eoan/farmer-registry/staff-api-1.2.2-rc.625:1.0.1-develop.57`. ECR tags are immutable, and deployments pin images by
digest. The naming follows oan-helm `docs/release/naming-standard.md`, section 6.

`helm/openg2p-farmer-registry/Chart.yaml` keeps `version: 0.0.0`. The build writes the real version into the archive
it packages.

## Release flow

1. **Merge to `develop`.** The build validates, publishes the images and deploys them to dev. It then publishes the
   packaged chart to oan-helm `repository/develop/`, where oan-helm's workflow updates the index, changelog and
   rollback history. See [dev delivery](dev-farmer-first.md#chart-packaging-and-publication).
2. **Merge `develop` into `staging`.** The staging build promotes the chart develop built from the same tree. It adds
   the rc tag to the same image digests, deploys to staging and publishes the rc chart. Nothing is rebuilt. See
   [merge through develop and staging](operations/merge-develop-staging.md).
3. **Production.** Not defined yet ([deployment](deployment.md#production)).

Before step 2, add the changes to [CHANGELOG.md](../CHANGELOG.md) under a heading for the version being promoted.

## Changing the platform version

Run `scripts/bump-rp-version.sh <version>`. It writes the six Dockerfiles, `Chart.yaml`, `Chart.lock` and the native
contract together, and these tests fail when the copies disagree:

- `test/unit/test_base_image_pin_lockstep.py`;
- `ci/build/check_rp_commit.py`, which checks the staff UI's platform commit;
- `test/unit/test_metadata_consistency.py`, which checks the platform's base model columns.

A platform bump also needs a fresh hosted acceptance run. See the
[native release contract](native-release-contract.md).

## Rollback

What the pipelines do today:

- Dev: the deploy is `--atomic`, so a failed upgrade puts the previous Helm revision back.
- A Helm rollback restores the chart and values, not data that hooks or users wrote.
- Data is restored only from a backup. See [rollback and recovery](deployment.md#rollback-and-recovery).

The rollback policy is still to be agreed: when a release is rolled back instead of fixed forward, who decides, and
how a database change is undone.
