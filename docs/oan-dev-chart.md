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

Before pausing builds or preparing backup evidence, run the same command with
`--rehearse`. It downloads/verifies the exact archive, reads a protected release
snapshot, lints, server-renders with the same post-renderer used for upgrade,
checks metadata-only preservation, and rechecks the Helm revision. It exits
before any upgrade or Job creation and writes a sanitized rehearsal artifact.
Backup evidence is mandatory for the actual upgrade; rehearsal does not attest
backup recovery or operational acceptance.

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

Helm's parent/child values coalescing reintroduces some explicitly nulled
environment defaults in this package. The reviewed `oan_compat.py` post-renderer
removes only its fixed allowlist of absent-installed defaults, only when BOTH
prepared `envVars` and `envVarsFrom` maps explicitly set the name to null. It
handles application and init containers together, verifies the dev.5 archive
again, and operates during both dev render and upgrade. It leaves commands,
images, routes, Secret references and all other configuration untouched.
Unknown changes still fail the independent preservation guard. This is a
deployment adapter for the pinned package; chart sources/packages are unchanged.
Normal dev preflight reads both the installed manifest and stored hooks, so the
existing IAM hook ConfigMap is covered by the resource inventory rather than
requiring an exception for new resources.

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

## Corrected rehearsal, 2026-10-21

The exact COSS dev.5 archive passes checksum/platform verification and strict
lint. A corrected read-only server rehearsal against installed revision 39
passes metadata-only preservation for all 32 persistent resources with installed
images retained. The deployment adapter resolves the environment-default issue.
The earlier apparent reporting-command encoding change came from Windows'
default subprocess decoding in the rehearsal tool. Explicit UTF-8 decoding shows
that the commands match; no command correction or comparison exception is used.

The production shell's `--rehearse` path also passes with a host-Python container
adapter on the dev host, which lacks Docker. CI separately exercises the Docker
helpers and Bash 4.3 shell control flow. This is preflight evidence only: no
cutover, schema mutation, Job execution, connector change or operational
acceptance was performed. Pause automatic dev deployments before merging the
Farmer PR, then use the backup-gated upgrade and acceptance sequence above.
