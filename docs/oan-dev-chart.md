# Pinned OAN Farmer dev deployments

Dev uses the exact package in [the approved profile](../ci/deploy/oan-chart.json),
copied from OAN's `environments/dev/farmer-jenkins.json`. The package SHA256,
chart version and bundled platform version are checked before lint, render or
upgrade. No dependency resolution or local-chart fallback runs for dev.
Staging retains its local chart, namespace `far` and existing evidence gates.

Jenkins' six recorded ECR digests select application images, including both
Celery workloads, db-seed, sanity and analytics. Saved values do not override
these pins. Installed environments, Secret references and dashboard settings
are reconciled through supported values. Preservation includes init containers,
optional images, resource inventory, selectors, Services, PVCs and ownership.

## Chart-only cutover

Do not merge automatically. After the Farmer and OAN profile PRs merge, pause
normal dev deployments and use a trusted Jenkins maintenance job on `vpn-agent2`.
Build `coss-ci/validation:$IMAGE_TAG` from the merged checkout. Bind
`farmer-dev-kubeconfig`; export `DELIVERY_ENVIRONMENT=dev`, `HELM_NAMESPACE=farmer`
and `HELM_RELEASE=farmer-registry`. Set `CUTOVER_BACKUP_DIRECTORY` to a private
directory on that agent and `REGISTRY_OUTCOME_FILE` to
`$PWD/service-outcomes/registry-cutover.json`. Run:

```sh
bash ci/deploy/cutover-dev.sh
```

The private directory must contain `release.json` (`helm status -o json`),
`values.json` (`helm get values -o json`), `manifest.yaml` (`helm get manifest`),
`hooks.yaml` (`helm get hooks`), `registry.dump`, `connector.dump`, and
`cutover-evidence.json`. Back up databases with the existing trusted operational
credentials, verify restoration, and retain those backups independently of the
Jenkins workspace. Do not archive them as Jenkins artifacts.

Evidence schema (replace every placeholder; hashes are lowercase SHA256):

```json
{
  "verifiedAt": "2026-10-21T00:00:00+00:00",
  "release": "farmer-registry",
  "namespace": "farmer",
  "helmRevision": 39,
  "applicationCommit": "<40-character installed application commit from Jenkins>",
  "restoreVerified": true,
  "reviewedJobRemovals": [],
  "sha256": {
    "release.json": "<hash>", "values.json": "<hash>",
    "manifest.yaml": "<hash>", "hooks.yaml": "<hash>",
    "registry.dump": "<hash>", "connector.dump": "<hash>"
  }
}
```

Evidence expires after one hour. `reviewedJobRemovals` must exactly name all
ordinary Jobs in the saved manifest. Inspect live Jobs too: active or unfinished
release Jobs block the upgrade. The command rereads release state and evidence
immediately before upgrading. A lost race or stale revision stops deployment.

The cutover keeps installed images, disables hooks, and filters ordinary Jobs
through `cutover-renderer.sh`. It never replays initialization after TTL cleanup.
Persistent resources must remain identical except the reviewed `helm.sh/chart`
metadata label. Named environment order is compared semantically. Unsupported
installed configuration blocks deployment. There is no automatic rollback.

Archive only `service-outcomes/*.json` and `service-outcomes/*.tsv`, including
the cutover result and later normal deployment results. Do not publish exported
values, rendered manifests, raw errors, DB dumps, tokens or login responses.
The cutover result explicitly leaves operational acceptance pending.

Before enabling normal builds, verify all workloads, canonical and legacy URLs,
staff login, authorized API access and dashboard health. Compare connector
settings/checkpoints with the protected baseline. Send one fresh marked
synthetic Farmer submission through ingestion, authorized approval and register
promotion. Record its sanitized outcome in the maintenance job; retain detailed
responses privately and do not replay historical submissions.

Normal sequence: build, verify ECR digests, download/verify pinned OAN archive,
guarded upgrade, rollout/schema/preservation checks, sanitized Jenkins outcome.
Keep schema migrations explicit, backed up and separately recoverable; Helm
rollback does not restore databases.

## Blocked rehearsal, 2026-10-21

The exact COSS dev.5 archive passed checksum/platform verification. A read-only
server render against installed revision 39 retained 32 persistent resources
and installed images but failed metadata-only preservation: added environment
defaults in API/Celery app and init containers, plus Unicode em-dash encoding
changes inside the reporting refresh CronJob command. That command has no chart
values override. No cutover, schema mutation, Job execution or connector change
was performed. Resolve this incompatibility through review before merging this
integration or enabling normal dev builds. Do not relax the guard or silently
change the approved package.
