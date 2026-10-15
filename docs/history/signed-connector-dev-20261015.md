> Historical evidence. Use [current operations](../operations/README.md) for maintenance; recorded commands and job links describe past rollouts.

# Coordinated services and Commons staff authentication

Farmer Registry owns `helm/openg2p-farmer-registry/values.yaml`'s
`cossAddons.components` catalogue, the environment overrides,
and the Jenkins coordination for Farmer services only. Registry, its connector,
and its dashboard frontend retain separate Helm releases. The existing
`dashboardApi` resources remain owned by the Registry
release. Optional API builds come from
`Centre-for-Open-Societal-Systems/farmer-registry-dashboard-api`; a strict guard
permits only its image to change, preserving all other persistent resources and
suppressing hooks and normal setup Jobs. The catalogue is consumed directly by
Jenkins, with no duplicate CI repository list.
No dashboard API is adopted by a new release. Livestock, crop, and shared OAN
dashboard releases are outside this pipeline; each registry owns its services.
The optional-service configuration rejects namespaces other than `farmer`.
No Helm values are committed back to Git automatically.

## Implementation and dev rollout

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
and task listing with HTTP 200. One labelled synthetic ODK intake completed both
approval stages under the unchanged live Farmer policy (201) and reached the
Register; photo, land certificate and geography were retained. The non-assignee
temporary validator received 403 and a master-realm token received 401. Temporary
Keycloak and ODK accounts were removed, the synthetic form closed and its test
partner disabled. No existing business record was approved. The replacement is now active in dev; the old release was retired after the
signed ingestion, approval, backup and checkpoint checks described below.

The connector source is `OpenG2P/registry-connector`, branch `develop`. Jenkins
resolves that branch once, fetches the exact commit into a temporary checkout,
and builds that detached commit. The inspected develop revision is
`bc565efd47c129ff0ce25809bd946afc2b5e70f5`: API Docker context `api`, UI context
`ui`, chart `api/deploy/charts/openg2p-connector`. API/worker/beat/consumer use the
same API image; UI uses a second image. Both digests are recorded and covered by
staging acceptance. Tags include the upstream commit and the Farmer overlay hash.

Upstream lacks attachment embedding. `integrations/registry-connector` adds a small transport adapter
around its polling/checkpoint implementation. It transfers referenced files into
Registry's existing File contract and aborts before yielding/checkpoint advancement
on missing, failed or oversized attachments. The API, worker and beat share an
isolated Celery queue, so replacement workers cannot consume old queued tasks.
No old service code is copied into the replacement image. API/UI builds, ten
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

`ci/validation/Jenkinsfile.worker-dev` supports a focused, opt-in deployment of this
worker fix before connector cutover. It publishes only the tested Farmer worker
image and updates the existing Registry release with that digest and its verified
staff token URL. Preflight compares every persistent rendered resource, including
Secrets and the dashboard API, against the installed manifest. Setup hooks are
suppressed and normal setup Jobs filtered from this image-only upgrade, preserving
their Secrets and ConfigMaps. No database migration is needed for this change.
The ordinary full Registry pipeline retains its own setup/acceptance requirements.

Live acceptance used the built replacement connector against an isolated Docker
database and a separate ODK project, with no scheduler. The Registry worker fix
was exercised in its built image for that one ingestion ID via SSH service routing;
this established ingestion acceptance before the worker rollout. Subsequently,
Jenkins `farmer-registry-worker-auth-dev/3` deployed the worker authentication fix
at Registry revision 12. Build 4 deployed the ODK attribution correction at
revision 13 from Farmer commit `68c1161bb2578137729a00b98dedba8bfcc4aae2`, with
worker digest `sha256:3ab041adc96a13d43841e85d0f30b94d1bf38cb36e5e2e6c18ce46591f21d39f`.
The installed worker passed the ODK actor check. No setup Jobs ran in these
focused upgrades. Intake and ingested change requests now persist ODK's
`survey_metadata.enumerator_name`, falling back to `__system.submitterName`, as
`created_by`; the form's Enumerator section uses the same precedence. This
display attribution does not confer Registry roles or approval permissions.
The live pipeline's `farmer-partner` was onboarded through Partner Management
with a newly generated RSA key pair. Its public key was approved only after
all old connector processes stopped. The private key remains in the retained
`farmer-connector-v2-signing` Secret; no private material entered Git or logs.
Earlier synthetic partners were disabled; the permanent partner remains active.
The named live approver approved through AWE. Registry's proxy statistics and
task listing also returned 200 with its required CSRF header; the initial proxy
403 was the test omitting that header, not missing approver roles.

The Farmer dashboard repository is `oan_farmerregistry_dashboard`. Its
develop/staging heads currently have no Dockerfile or application code and are
skipped. The Farmer dashboard API remains in the existing Farmer Registry release,
with independent image builds and an image-only deployment guard. Its existing
live contract passed Postman with 17 requests and 50 assertions, exit 0. Save
reviewed, nonsecret overrides as `helm/environments/dev/services/<component>.yaml` and separately
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

`helm/environments/dev/registry-identity.yaml` is the canonical Registry overlay for
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

Run `scripts/operations/identity/check.py` from a host with network access using private effective
provider JSON, mounted effective AWE YAML, internal JWKS JSON, and operator review:

```bash
python scripts/operations/identity/check.py --provider /private/provider.json \
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
   reviewed upstream Helm values only after those checks. Preparation never performs activation. Signing, final checkpoint reconciliation
   and a rehearsed rollback are required before the separate handoff.

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

The initial protected snapshot is retained at
`/var/backups/farmer-connector-20261015-before-replacement/snapshot-validated`
(SHA256 `c4cdb2bb37049b00470994d6443ec9b562c3548d267b27df3bb1e0a6eddd48c1`).
Its full 201,326,775-byte dump was restored and rehearsed in isolated PostgreSQL.
The final stopped-source snapshot is
`/var/backups/farmer-connector-20261015-final-paused/snapshot`
(SHA256 `261ca69a23e704d7c80b25a2420ad955eba6063323ceaf88f7e9d2f6e2c3270c`).
All four restored tables matched the frozen source before the replacement's
pipeline was paused. No old successful runs or previously accepted partner records
existed to reconcile. The old shared queue was empty, with no active, reserved or
scheduled Farmer tasks; no shared queue was purged.

The final pre-retirement snapshot is
`/var/backups/farmer-connector-20261015-before-retirement/snapshot`
(SHA256 `e535a6c23f1edb5c9d30967ec3150af237aff1331a81f05712590b656c5c864a`),
including a 246,226,417-byte database dump and old Helm revision 5. Backups are
protected private operator files, never Jenkins artifacts. Retirement verified
live Helm ownership, stopped workloads, replacement digests, acceptance and
backup integrity. The old release was uninstalled with hooks suppressed and
history retained. Its database, backups, shared PostgreSQL/Redis and retained
credential Secrets remain intact.

## Signing, checkpoints and live acceptance

The connector signs the G2P envelope with RS256, a pinned partner/key ID, a
five-minute expiry, message ID and canonical message SHA256. Farmer's Partner API
fetches the key only from the configured Partner Management service and validates
issuer, algorithm, expiry and message binding. The actual deployed API rejects
unsigned, tampered, wrong-key and expired requests with HTTP 401. A transaction
lock and partner/model/message-ID lookup return the original correlation ID on
identical signed retries; a changed body cannot reuse the message ID.

Polling stops at a failed record, preserving the last successful boundary for
retry. The isolated rehearsal tests this failure boundary, schema reruns, injected
DDL recovery and checkpoint/idempotency transfer into a separate recovery database.
An injected recovery write failure rolls back the copied run and key together;
a subsequent retry succeeds and its rerun copies nothing. Recovery requires both
pipelines paused and no in-progress runs. Do not blindly restart the original
unsigned connector after signature enforcement: stop replacement ingestion,
reconcile its successful keys/checkpoint using `coss_connector.recovery`, and
restore a signing-compatible image/key configuration before enabling old workers.
Never run both schedulers concurrently.

Jenkins coordinated build
[`farmer-registry-services-dev/11`](https://jenkins.oanstaging.com/job/farmer-registry-services-dev/11/)
used Farmer source `d13c36dc4302515516839bedea1b2f049d9a8c88` and connector source
`bc565efd47c129ff0ce25809bd946afc2b5e70f5`. Connector API digest is
`sha256:3a042f7a2d04e4e9ff8fdd2614f36a678cb6294f36ffc40d7d687bd33cb1c0c2`;
UI digest is `sha256:05a7e2c2e7de3088a5cd7092899c760387840e4236ca67aaa6620a830aa8cb6e`.
The replacement was accepted paused, then its route ownership and scheduler were
activated through guarded Helm upgrades. Its active Helm revision is 10, with
API/worker/UI and one beat, isolated queue `farmer-registry-connector-v2`, and
consumer disabled. The live project-1 pipeline retains its ODK mapping and
`farmer-partner` identity. Its first poll ingested one source record successfully;
that business record was not approved during testing.

Jenkins focused signing build
[`farmer-registry-signing-dev/5`](https://jenkins.oanstaging.com/job/farmer-registry-signing-dev/5/)
deployed Partner API source `4afa7401c68e081d1015832739e6d6403141b5f7`, digest
`sha256:2766d684885b9f24378fe00f8e4b36ddfd1d771e17afb34f203559d56189a5a7`.
Farmer Registry is at Helm revision 22; its previously verified attribution/AWE
worker remains unchanged. The dashboard API source is
`85fd0a3c251855ee48b9654fa5c8d2cf30d7bc81`, digest
`sha256:07c3bc33988850af07dc473f62c50effa5b9257000ba8e201e75d47f128b19ca`,
with existing Registry ownership preserved. The dashboard frontend remains skipped
because its develop branch contains no application build files.

A separate project-5 synthetic ODK submission traversed the deployed native
Run Now API and Celery worker, signed Partner API, Registry intake and both
unchanged live-policy approval stages. It reached the Register with both files,
geography and the ODK collector name intact on the actual intake screen. A repeat
poll fetched zero records with exactly one successful run/key. Re-signed delivery
retries returned the original Registry correlation. A separate synthetic web
intake passed save, readback, finalization, actual screen checks and both portal
approval stages, then reached the Register. Fresh portal task statistics/listing
and decisions passed using its access token and CSRF header. No existing business
record was approved. The synthetic connector is disabled and paused with its
credentials scrubbed; its temporary ODK account was deleted and form closed.
The permanent partner remains active.

The ordinary preparation job skips an already active connector; it cannot reset
its replicas or credentials. `helm/environments/dev/services/registry-connector-active.yaml`
records the operator activation values and is not automatically applied by that
job. Future active-image upgrades require their own accepted rollout. Public
connector API health and UI both return HTTP 200 after routing handoff.

Staging identity/configuration remains unverified and staging deployment stays
disabled. Promote the accepted dev connector digests without rebuilding only after
its own identity, storage and environment gates pass.

The final Linux Jenkins validation-only run
[`farmer-registry-services-dev/13`](https://jenkins.oanstaging.com/job/farmer-registry-services-dev/13/)
passed 365 tests and 57 subtests plus ODK transform and deployment shell checks.
It did not rebuild or deploy services. Ten connector adapter tests, three actual
Partner API runtime tests, schema/failure/checkpoint recovery rehearsals and
Helm credential retention checks also passed during preparation.

A fresh Postman dashboard contract run after activation passed 17 requests and
50 assertions with exit 0. The nonsecret deployment/acceptance record is
[`rollouts/2026-10-15-farmer-dev.json`](../rollouts/2026-10-15-farmer-dev.json).
The two anonymous AWE requests each passed their expected HTTP 401 assertion;
this installed CLI exits 1 on HTTP 401 despite passing assertions.
