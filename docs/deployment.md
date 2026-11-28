# Deployment

How the Farmer Registry reaches each environment, and where the detailed procedures are. Each change goes through
Jenkins. Never run `helm` or `psql` against an environment by hand.

## What is deployed

One Helm release, `farmer-registry`: the chart `helm/openg2p-farmer-registry`, which wraps the OpenG2P `openg2p-registry`
chart at the platform version pinned by `ARG BASE_IMAGE_VERSION` in `docker/*/Dockerfile`. It runs six images built here:
staff-ui, staff-api, partner-api, celery (worker and beat), db-seed and sanity-tests. Their names follow
[`ci/deploy/image_names.py`](../ci/deploy/image_names.py).

These are separate releases with their own delivery: the connector, the dashboards, Crop, Livestock and the shared
Commons services. See [service coordination](operations/coordinated-services-rollout.md) and
[dashboard delivery](dashboard-delivery.md).

On install and on every upgrade, the post-install hooks replay the seed (`meta_data/`, `awe_meta_data/`) and run the
sanity smoke tests. The seed is idempotent (`test/unit/test_seed_on_conflict.py`), and `site-configuration/90_checks.sql` fails
the hook when the forms are wrong.

## Environments

| | Dev | Staging | Production |
| --- | --- | --- | --- |
| Source branch | `develop` | `staging` | not defined yet |
| Pipeline | [`ci/pipelines/dev.groovy`](../ci/pipelines/dev.groovy) | [`ci/pipelines/staging.groovy`](../ci/pipelines/staging.groovy) | not defined yet |
| Namespace, release | `farmer`, `farmer-registry` | `farmer`, `farmer-registry` | not defined yet |
| Registry UI | `https://farmer-registry.development.oanstaging.com` | `https://farmer-registry.oanstaging.com` | not defined yet |
| Chart installed | the chart the build packaged; [`oan-chart.json`](../ci/deploy/oan-chart.json) for a deploy run by hand | the rc of the chart develop built from the same tree; [`oan-chart-staging.json`](../ci/deploy/oan-chart-staging.json) for operator actions | not defined yet |

The legacy staging release in namespace `far` (platform rc.544) is not touched by these pipelines.

### Dev

A merge into `develop` validates, builds and publishes the images. It then upgrades the dev release with them and
publishes the chart to oan-helm `repository/develop/`. There is no separate deploy button. Details:
[dev delivery](dev-farmer-first.md).

| `DELIVERY_ACTION` | Effect |
| --- | --- |
| `deploy` (default) | Upgrades the existing release (`ci/deploy/deploy-dev.sh`). |
| `fresh-install` | Archives both databases, uninstalls, drops them, and installs again from an empty database. Deliberate only. |

### Staging

A merge into `staging` from `develop` promotes the chart develop built from that tree. The images are the
same digests under an rc version, so nothing is rebuilt. If develop never built the tree, the build fails. The
connector and dashboard UI releases follow on the same promotion. `fresh-install` and `deploy` are operator actions
in [`Jenkinsfile.operator`](../Jenkinsfile.operator). They need protected rehearsal evidence. Details:
[merge through develop and staging](operations/merge-develop-staging.md) and
[staging upgrade](operations/staging-upgrade.md).

### Production

Not defined yet. Open questions, to be decided before this section is written:

- the cluster, namespace and the Commons endpoints (Keycloak, ODK Central, MinIO) production uses;
- the backup method and when it runs;
- the rollback policy (see [release](release.md#rollback)).

## Gates before a deploy

- Every GitHub check of the commit is green ([`ci/deploy/require-green-checks.sh`](../ci/deploy/require-green-checks.sh)).
  This includes [`ci/validation/validate.sh`](../ci/README.md#validationvalidatesh) and the chart lint and render.
- Every image the packaged chart pins pulls by digest in the target namespace (`ci/deploy/pull_check.py`).
- The installed chart matches its pin (version, SHA-256 and platform version, `ci/deploy/oan_chart.py`). An operator
  action never installs a chart older than the running one.

## Rollback and recovery

- Dev `deploy`: the upgrade is `--atomic`. If it or its hooks fail, Helm puts the previous revision back and the build
  fails.
- Staging promotion rolls back on failure (oan-helm `deliver_staging.sh`). Staging operator actions keep automatic
  rollback off across schema migrations.
- A release left `failed` is recovered by the next build without automatic rollback, so an older revision is not put
  back over database changes the failed one already made.
- A Helm rollback restores the chart and values, not data. Data is restored from a backup: on dev, the archive that
  `fresh-install` writes before it drops the databases ([dev delivery](dev-farmer-first.md#fresh-install)). On
  staging, the evidence the [staging upgrade](operations/staging-upgrade.md) requires.
