# Farmer service coordination

The root Jenkinsfile selects one environment pipeline. Dev runs Registry first,
then coordinates the three Farmer-owned add-ons from `cossAddons.components` in
the owning chart values. Other registry dashboards and shared dashboards remain
outside Farmer ownership.

- Dashboard branches are `develop` for dev and `staging` for staging. Missing
  branches/application files are skipped while preserving existing deployments.
- Authentication, network, build and deployment errors are failures. Independent
  optional components continue; Jenkins becomes unstable.
- Dashboard API stays embedded in the Registry release. Dev promotion permits
  its pinned image and the four reviewed authentication environment literals;
  the guard preserves all other fields, resources, routes, Secrets and workloads.
  Staging retains its image-only guard.
- Ordinary preparation skips the active dev replacement connector and cannot
  reset its replicas, credentials or ingestion state.
- Connector cutover and upgrades require explicit rehearsal and acceptance.
  Staging promotion requires accepted dev digests and separately verified staging
  identity/configuration. Staging prepares the replacement paused; scheduler
  activation and retirement remain separate acceptance-gated operator commands.

Dev service values are under `helm/environments/dev/services/`. The active overlay
is operator-only; it must not replace the paused preparation overlay. Runtime
adapters build from `integrations/registry-connector/`.

Artifacts record source commits, image digests, Helm revisions and component
outcomes. Raw values, backups, credentials and rendered Secrets remain private.
Helm failures also include fixed diagnostic categories in `deploy.json`, such as
readiness timeout, image pull failure or a failed lifecycle hook.

The dev API overlay explicitly enables authentication, discovers trusted issuers
through the Commons IAM Service in the `commons` namespace, and requires the
`charts:read` role on audience `farmer-registry-dashboard-api`. These settings
must accompany the authenticated API image: without an IAM URL or issuer the
application fails at startup. Do not disable authentication to pass readiness.
The coordinator checks the rendered authentication literals both before upgrade
and in the final Helm manifest; it rejects missing, duplicate or altered values.
The UI is deployed only after the API promotion succeeds. A green image build
or a skipped UI is not evidence of dashboard delivery.

After promotion, check API readiness, rejection of unauthenticated chart calls,
an authorized chart response, and the UI's authenticated backend requests. On
failure inspect Helm history and pod events/logs to establish the final state;
an atomic upgrade request alone does not prove a successful rollback.

See [delivery](README.md), [signing and recovery](connector.md), and
[staging cutover](staging-upgrade.md). The [accepted dev rollout
evidence](../history/signed-connector-dev-20261015.md) does not establish staging acceptance.
