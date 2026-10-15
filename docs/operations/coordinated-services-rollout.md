# Farmer service coordination

The root Jenkinsfile selects one environment pipeline. Dev runs Registry first,
then coordinates the three Farmer-owned add-ons from `cossAddons.components` in
the owning chart values. Other registry dashboards and shared dashboards remain
outside Farmer ownership.

- Dashboard branches are `develop` for dev and `staging` for staging. Missing
  branches/application files are skipped while preserving existing deployments.
- Authentication, network, build and deployment errors are failures. Independent
  optional components continue; Jenkins becomes unstable.
- Dashboard API stays embedded in the Registry release. Its image-only guard
  preserves the other resources, routes, Secrets, storage and workloads.
- Ordinary preparation skips the active dev replacement connector and cannot
  reset its replicas, credentials or ingestion state.
- Connector cutover and upgrades require explicit rehearsal and acceptance.
  Staging promotion requires accepted dev digests and separately verified staging
  identity/configuration. No staging replacement is enabled by this cleanup.

Dev service values are under `helm/environments/dev/services/`. The active overlay
is operator-only; it must not replace the paused preparation overlay. Runtime
adapters build from `integrations/registry-connector/`.

Artifacts record source commits, image digests, Helm revisions and component
outcomes. Raw values, backups, credentials and rendered Secrets remain private.

See [delivery](README.md), [signing and recovery](connector.md), and
[accepted rollout evidence](../history/signed-connector-dev-20261015.md).
