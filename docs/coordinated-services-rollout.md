# Coordinated services and Commons staff authentication

Farmer Registry owns `ci/services/components.yaml`, the environment overrides,
and the Jenkins coordination for Farmer services only. Registry, its connector,
and its dashboard frontend retain separate Helm releases. The existing
`dashboardApi` resources remain owned by the Registry
release, with their independently published image retained by its existing guard.
No dashboard API is adopted by a new release. Livestock, crop, and shared OAN
dashboard releases are outside this pipeline; each registry owns its services.
The optional-service configuration rejects namespaces other than `farmer`.
No Helm values are committed back to Git automatically.

## Implementation and remaining inputs

The root Jenkins pipeline builds optional services on `develop`, records source
commits and pushed image digests, and upgrades them independently after Registry.
A missing branch (Git exit 2), missing application files, or missing environment
values skips that component and preserves its deployment. Authentication, network,
build, image publication, validation, and deployment errors mark Jenkins unstable;
other optional components continue. Registry errors remain fatal. A reused Jenkins
workspace cannot contribute outcomes from an earlier run.

Suresh's latest upstream changes were fetched and integrated at `7a055b2` (PR 99).
They move new-dev public services to `*-development.oanstaging.com`. Live OIDC
discovery confirms the Commons staff realm now advertises
`https://keycloak-development.oanstaging.com/realms/staff`; the old Commons
hostname is an alias, not a different realm. Do not restore the former issuer
literal simply because it appeared in an earlier rollout plan.

Read-only live checks found IAM, Registry and effective AWE configuration already
aligned. A fresh Registry service token reached AWE task statistics and listing
with HTTP 200; missing-token calls returned 401. The public and internal JWKS
contain identical realm keys. A temporary Intake Validator completed a fresh
browser login through Registry and IAM; its access token reached AWE statistics
and task listing with HTTP 200. Authorized approval of a synthetic intake
remains an acceptance gate. No business record was approved
and the existing connector was not stopped, replaced or uninstalled.

The connector source is `OpenG2P/registry-connector`, branch `develop`. Jenkins
resolves that branch once, fetches the exact commit into a temporary checkout,
and builds that detached commit. The inspected develop revision is
`bc565efd47c129ff0ce25809bd946afc2b5e70f5`: API Docker context `api`, UI context
`ui`, chart `api/deploy/charts/openg2p-connector`. API/worker/beat/consumer use the
same API image; UI uses a second image. Both digests are recorded and covered by
staging acceptance. Tags include the upstream commit and the Farmer overlay hash.

Upstream lacks attachment embedding. `ci/connector` adds a small transport adapter
around its polling/checkpoint implementation. It transfers referenced files into
Registry's existing File contract and aborts before yielding/checkpoint advancement
on missing, failed or oversized attachments. The API, worker and beat share an
isolated Celery queue, so replacement workers cannot consume old queued tasks.
No old service code is copied into the replacement image. API/UI builds, eight
adapter tests and isolated PostgreSQL schema/deduplication rehearsal passed.

Live polling exposed an upstream clock/schema mismatch: the worker assigns an
aware UTC timestamp to its naive `last_poll_at` column. The connector adapter
normalizes this one field to naive UTC, preserving existing stored values. The
rehearsal now runs the real poll worker twice and requires timestamp persistence.

The pinned Registry worker also omitted the bearer token when automatically
finalizing ingested intake. The Farmer Celery image now applies a small,
build-time checked change to that exact call and obtains a cached client
credentials token from its configured AWE token URL. Missing credentials or token
errors stop finalization. Public token routing stays in the owning identity values;
issuer, signature, TLS and approval authorization checks remain enabled.

The Farmer dashboard repository is `oan_farmerregistry_dashboard`. Its
develop/staging heads currently have no Dockerfile or application code and are
skipped. The Farmer dashboard API remains in the existing Farmer Registry release,
with its independently published image retained. Save
reviewed, nonsecret overrides as `ci/services/dev/<component>.yaml` and separately
as `ci/services/staging/<component>.yaml`. Every file needs:

```yaml
_coordination:
  namespace: farmer # must match the reviewed component namespace
# Normal Helm values below; existing values are retained and merged.
```

Review dashboard IAM routing, cookie domain, logout, service-to-service audience,
dashboard API URL, image pull configuration and reporting-view compatibility.
Existing charts needing unreviewed routing/credential/storage changes stop at the
preservation gate; perform those as a separate reviewed migration. A missing
dashboard release is skipped. A new connector release may be installed only with
verified backup/storage isolation and all processes paused.

Optional coordination uses `ci/services/Dockerfile` on both Jenkins agents: Python,
Git, Docker CLI/buildx, AWS CLI, Helm 3.19.0 and PyYAML. No host Python/venv is
required. Build operations use the agent's existing Docker socket; deployment
receives only the bound kubeconfig and private backup mount, without a Docker
socket. Both run as the Jenkins user's UID/GID. ECR repositories
`openg2p/<component>` (or `<component>-api`/`-ui`) must exist with push/pull
permissions. Missing tooling or permissions are failures, not missing-code skips.

Only `service-outcomes/*.json` and the Registry image provenance TSV are archived.
They contain source, commit, digest, namespace, Helm revision and outcome fields.
Temporary release values, rendered manifests, Docker login configuration, token
files and private backup exports are never archived. Tool errors use fixed
categories; inspect private infrastructure logs for details.

## Identity migration

`ci/identity/registry-new-dev.values.yaml` is the canonical Registry overlay for
the Commons public staff issuer:
`https://keycloak-development.oanstaging.com/realms/staff`. It updates UI IAM and
logout, API IAM/token endpoints, and worker token endpoints together. It changes
no client secret, callback credential, database, cookie scope, ingress, or AWE
validation setting. The overlay is merged into the values persisted by Helm.

Before enabling it, inspect the effective shared IAM provider, both staff portal
login routes, Commons client registrations, existing staff users, user/client
roles, service-account credentials and AWE audience. Configure the existing IAM
provider through its owning Commons configuration/migration workflow; a Registry
UI hostname change cannot migrate IAM's stored provider or its client secrets.
Shared IAM changes affect other registries: verify their login routes too.
This checkout does not contain the owning Commons chart/provider migration, so
that change must be reviewed against its actual version and effective values.

Do not disable AWE issuer/signature checks. Preserve AWE's existing internal
JWKS URL when it returns the same public key material as the public staff realm.
The readiness tool verifies equality of public key material, not just key IDs.
It does not modify AWE configuration or verify a JWT signature itself.

Run `ci/identity/check.py` from a host with network access using private effective
provider JSON, mounted effective AWE YAML, internal JWKS JSON, and operator review:

```bash
python ci/identity/check.py --provider /private/provider.json \
  --awe-config /private/awe-config.yaml --internal-jwks-file /private/jwks.json \
  --review /private/realm-review.json --output /private/identity-evidence.json
```

The review must contain `environment: dev`, the exact `issuer`, `aweAudience`
matching the effective AWE setting, and every boolean named by `CHECKS` in the
tool. These are operator attestations to actual inspection/rehearsal, not tests
inferred by the tool. Verify the pinned worker image actually consumes the token
settings in the overlay. `--token-file` optionally inspects **only** the token's
issuer; do not send tokens to logs or commit them.

Bind the resulting short-lived file as Jenkins Secret File
`farmer-dev-identity-evidence` and explicitly enable `APPLY_COMMONS_IDENTITY`.
Evidence expires after one hour and is bound to the exact overlay bytes. The
normal environment/Secret preservation guard stays enabled, with only the exact
identity variables allowed to change. Authentication changes are off by default.

After deployment, end old IAM/Keycloak sessions and sign in freshly. Verify task
statistics, task listing and a role-authorized approval. Send a validly signed
token from the old/wrong issuer and confirm rejection. A successful Helm upgrade
or decoded JWT is not evidence of these authorization checks.

## Connector inventory, preparation and cutover

1. Export the old connector's pipelines, mappings and checkpoints. Take a
   PostgreSQL custom-format dump of its actual database. Run the backup tool on
   these private files; the destination must be new:

   ```bash
   python ci/services/connector_cutover.py backup --directory /private/connector-backup \
     --pipelines /private/pipelines.json --mappings /private/mappings.json \
     --checkpoints /private/checkpoints.json --database /private/database.dump
   ```

   This also saves the old Helm values, manifest and hooks, hashes every export,
   and validates the dump's directory using `pg_restore --list`. Rehearse a full
   restore separately; a valid dump header does not prove recoverability. Copy
   the backup directory to retained private storage. Never put it in Jenkins
   artifacts or Git.

2. Inspect the upstream connector commit and migrate required ODK pipelines and
   mappings into an isolated database. Rehearse every enabled migration and hook
   against isolated databases, including reruns and injected failures/recovery.
   Disable upstream init jobs after separately preparing the isolated database
   if necessary: preparation rejects all Jobs, DaemonSets, active Deployments,
   active StatefulSets and unsuspended CronJobs. It does not enable ingestion.

3. The inspected upstream image paths are already configured. Supply private
   `CONNECTOR_BACKUP_DIRECTORY` on the optional deployment agent and add these
   reviewed `_coordination` fields to the environment values: `backupHash`
   (SHA256 of backup.json), `database` (new database name), `databaseEnv` and
   `oldDatabaseEnv` (the real rendered database-name variables). The guard requires
   a different rendered database from the old connector and disjoint PVCs.
   Secret-only/unknown database wiring fails closed for explicit review.

4. Verify fresh-login AWE statistics/listing/approval **before** cutover. Pause
   the old connector's scheduling and workers, wait for in-flight work and queues
   to drain, take a final checkpoint export/dump, and reconcile it with the migrated
   pipelines. Save a new immutable backup directory after pausing and use its
   hash for acceptance/retirement; retirement rejects a changed old Helm revision.
   Do not run both schedulers. Enable the replacement through its
   reviewed upstream Helm values only after those checks. Activation and format
   conversion cannot be scripted correctly until upstream code is inspected.

5. Submit a synthetic ODK record. Verify every attachment in Registry, replay the
   same submission and prove duplicate prevention, verify Registry intake and
   AWE task creation, then approve with an authorized fresh session. Keep record
   identifiers and test results in private acceptance evidence. Check dashboard
   health and reporting after reporting refresh.

6. Retirement is a separate command, never an automatic result of a build or skip.
   `connector_cutover.py retire --directory /private/connector-backup
   --acceptance /private/connector-acceptance.json` requires all booleans in
   `ACCEPTANCE`, environment `dev`, the backup hash, the accepted replacement
   `helmRevision` and `digest`. It rereads both releases, verifies the accepted
   replacement digest, checks old workers/jobs/scheduling are stopped, rejects
   shared resources and unprotected storage, and uninstalls **only**
   `farmer-connector` with hooks disabled and history retained. Releases containing
   database StatefulSets, unknown resource kinds or existing hook resources stop
   for explicit migration review. Databases and backups are never deleted.

On failure, stop replacement ingestion first. Preserve its checkpoints, dump,
logs and partial Registry/attachment results. Reconcile source submission IDs,
attachment completion, duplicates and last committed checkpoints before restoring
the old configuration/workers. Do not assume Helm rollback undoes database or
Registry writes. Verify synthetic replay after recovery. The coordinator's atomic
rollback covers optional release resources only.

## Hook evidence and staging

For optional charts with hooks, commit a reviewed nonsecret record at
`ci/services/<environment>/rehearsals/<component>.json`, containing `commit`,
`digest`, `chartHash`, `environment`, `valuesHash` and true booleans
`isolatedDatabases`, `everyEnabledHook`, `rerun`, `failureRecovery`. `valuesHash`
is SHA256 of `json.dumps(overrides_without__coordination, sort_keys=True).encode()`.
The record must describe actual isolated rehearsal results for that exact image,
chart and values. Hook evidence does not substitute for end-to-end acceptance.

Configure a separate Jenkins job with `ci/services/Jenkinsfile.staging` only after
dev acceptance and staging configuration verification. `ENABLE_STAGING` defaults
to false. Bind `farmer-staging-kubeconfig`, `farmer-services-tested-dev-manifest`
(the dev **deployment** outcome JSON), and `farmer-services-dev-acceptance` as
Secret Files. The acceptance JSON needs the matching `configHash`, connector
digest under `images.registry-connector`, and all checks listed in the
coordinator's staging acceptance validation. Staging's own IAM realm, audience,
callbacks, cookie domains, storage and namespaces must be verified independently.
Do not reuse the dev identity overlay for staging.

Staging resolves dashboard repositories' `staging` branches without falling back
to `develop`. The connector reuses the accepted dev source commit and image
digest with no rebuild. Missing branches/application files preserve existing
services; genuine failures continue independent components and mark unstable.
The staging coordinator does not deploy Registry or remove the old connector.

The initial protected snapshot is retained on new dev at
`/var/backups/farmer-connector-20261015-before-replacement/snapshot-validated`.
Its custom-format dump is 201,326,775 bytes. A protected local copy was verified
against its SHA256, fully restored into an isolated Docker PostgreSQL, and tested
with the built replacement API. Schema reruns, injected DDL rollback/recovery,
original-column row checksums and duplicate-send suppression all passed. Existing
database/configuration were read only. The checked-in dev values are preparation
values: API/worker/UI at zero replicas, beat/consumer disabled, ingress disabled,
and database name `farmer_connector_v2`. Provision and verify the DB Secret before
activation; the prepared manifest does not create it or claim ingestion readiness.

Local regression tests cover branch/network classification, exact commit and
digest selection, independent failures, Helm mutation ordering/race prevention,
identity allowlists, issuer/JWKS/audience prerequisites, isolated storage and
retirement preservation. Live ingestion, authorization, hook rehearsals and
Jenkins execution remain required rollout evidence.

The Linux container validation suite passed 273 tests and 57 subtests; an
additional finalizer integration test also passed in the focused eight-test worker
authentication suite. Nine connector adapter tests passed against the built image.
The ODK transform and deployment shell harness passed on Bash 4.3, 5.2 and 5.3.
Both Jenkinsfiles passed the live Jenkins Declarative Pipeline validator. The
actual upstream chart and locked dependencies rendered six preparation resources;
guards confirmed separate storage, no active ingestion and no ingress. The helper
image's Python/Git/Docker/AWS/Helm tools were verified, including Docker access as
a non-root UID. These checks do not establish live ODK-to-approval acceptance,
optional setup-hook rehearsal, image publication or staging readiness.

Postman also ran the two anonymous AWE calls with one passing 401 assertion per
request. This installed CLI returns exit 1 for HTTP 401 even with passing tests;
inspect the assertion summary when running these expected-denial checks.
