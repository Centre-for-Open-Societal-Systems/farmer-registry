# Farmer staging RC upgrade and signed ODK cutover

For the newly authorized test-data reset, use the [reset procedure](staging-reset.md)
instead of reconciling the old Kamuntu business records in place. The reset
retains a protected archive and initializes metadata only; it does not change
the requirements for backup, rehearsal, partner readiness or signed acceptance.

Changes land in `develop` first. Promote the accepted `develop` branch into
`staging`; do not merge a feature branch directly into `staging`. The migration
branch includes the reviewed staging history, but its PR targets `develop`.
This procedure upgrades only Farmer in `far`, through the existing
`Gen2-Package/farmer-registry` multibranch job. Merging into `staging` validates;
`DEPLOY_STAGING=false` remains the default. Registry deployment is fatal on
failure; optional services release independently and failures mark Jenkins unstable.

The rollout manifest records current
implementation and execution status. Historical revision 36 / connector revision 3
are inspection findings, not permission to assume the cluster is still unchanged.
Refresh remote refs and live inventories before review. The [map tile follow-up](odk-map-tiles.md) records the verified dev and public staging repairs. The ODK location update is published
as form 1.0.5. Registry and legacy connector revisions remain 36 and 3. The latest
inspection found legacy Farmer geography references and missing Farmer partner
registration; do not enter maintenance or authorize deployment until those
prerequisites and the remaining rehearsals pass. The separately reviewed
shared-geography repair was authorized and applied.
Master Data now matches the canonical seed; the credential reference blocking
its API was corrected to the owning Commons Helm values.

## Fixed environment contract

| Resource | Staging |
| --- | --- |
| Namespace / Registry release | `far` / `farmer-registry` |
| Platform | `1.2.2-rc.544`, committed `Chart.lock` |
| Registry database | `farmer_registry_far`, retain its current role/Secret |
| Kubeconfig credential | `staging-farmer-kubeconfig` |
| Staff issuer | `https://keycloak.oanstaging.com/realms/staff` |
| Legacy connector / database | `farmer-connector` / `farmer_connector_far` |
| Replacement connector | `farmer-registry-connector` |
| Replacement database / role | `farmer_connector_v2_far` / `far_farmer_connector_v2_user` |
| Queue | `farmer-registry-connector-v2-far` |
| Signing Secret / key ID | `farmer-connector-v2-far-signing` / `farmer-connector-v2-far` |
| Partner | retain `farmer-partner` |
| ODK | `https://odk-central.oanstaging.com`, project `1`, `farmer_profile` |

Owning values live in `helm/environments/staging/`. Effective installed Registry
values are the starting point. Retain routes, storage, callback URLs, databases,
Secret references and dashboard images. The shared RC helper rejects cross-environment
credentials, API servers and resources, checks all 36 coordinate columns plus
document history, and binds persistent candidate resources to their rehearsed hash.
Rendering uses server-side lookups so existing Secrets survive. Private values,
manifests, authentication files and dumps must never become Jenkins artifacts.

The optional `publicStaffUi` template and its `-staff-portal-ui-pub` Service
are retained from staging's chart. Saved values control whether it exists;
the default stays disabled. Its origin, cookie/IAM settings and mounted volumes
survive, and its image must match the accepted staff-UI digest.

## Prepare and rehearse before maintenance

1. Refresh the cached develop/staging refs and inspect their diff. Rebase/merge the
   migration branch as needed; review every staging-specific resolution. The
   cached staging-only commits contained merges, without an additional source diff.
   Open and review the change PR targeting `develop`. After develop validation
   and acceptance, open the promotion PR from `develop` to `staging`. The PR
   check rejects another source branch for staging. Do not enable staging
   deployment on merge. Develop retains its existing automatic dev deployment.
2. On a trusted staging host, bind the staging kubeconfig and set
   `KUBECONFIG_CREDENTIAL=staging-farmer-kubeconfig`. Inventory both Helm releases,
   manifests, hooks, exact effective values and revisions. Keep a private journal
   under a new `/var/lib/registry-coordination/farmer-staging-<run>/` directory.
3. Take protected custom-format dumps of `farmer_registry_far` and
   `farmer_connector_far`; export ODK form XML, version history and every media file.
   Export pipeline identity, source configuration, mappings, failed/successful run
   history, idempotency keys and checkpoints. The connector helper is:

   ```bash
   python scripts/operations/connector/inventory.py --environment staging \
     --directory /var/backups/farmer-staging-<run>-initial/connector
   ```

   It retains failed statuses verbatim in `run-history.json` and the complete dump.
   Verify SHA-256 sums and copy the backup tree to approved protected durable
   storage. Never use the dev-only SSH snapshot fetcher for staging.
4. Fully restore both dumps into disposable PostgreSQL databases, never into live
   staging. Verify row counts, failed statuses, attachments and checkpoint state.
   Rehearse `scripts/migrate-rp-geo-columns.sh` with PostgreSQL 16 tools, then
   `scripts/operations/commons/migrations/document_history_event_type.sql`.
   Invalid nonempty coordinates must abort; reruns must preserve data. Run the
   candidate application migrations, metadata seed, reporting refresh and every
   enabled hook using isolated dependencies. Inject failures and prove recovery.
   Retain restore and hook logs privately. `pg_restore --list` is only a format
   check and does not establish a successful restore.
5. Rehearse the exact accepted connector API digest against the legacy dump using
   `scripts/operations/connector/rehearse.py <api-image@digest> --backup <dump>`.
   Do not rebuild either accepted connector image. The staging chart adds the
   dedicated queue; record its separately rehearsed `connectorChartHash` as well
   as the original dev chart hash, overlay hashes, image digests and dev revision.
6. Export the shared geography and all Farmer geography references, then run
   `scripts/check-odk-geo-compatibility.py --catalog <catalog.json> --references
   <references.json>`. Require exact canonical IDs and relationships. Do not change
   the shared catalogue. Rehearse publishing canonical Farmer media as a new form
   version. Account for the 35 staging-only Kebele IDs; preserve all submissions
   and form history, including the existing submission's canonical selection.
7. Diagnose the legacy partner failures from protected run evidence. Verify
   `farmer-partner`, authorized models/routing and key registration requirements.
   Inspect the failed Commons release separately. Repair only a proven
   Farmer-blocking prerequisite through its owning release, with separate evidence.
   This pipeline does not upgrade Commons.
8. Verify staging IAM/AWE using `scripts/operations/identity/check.py --environment
   staging` and its private provider, effective AWE config, review and internal
   JWKS inputs. It checks the public staff issuer, audience, provider callbacks
   and matching public/internal realm keys. Keep the existing internal staff JWKS
   endpoint and issuer/signature enforcement. Configuration checks alone do not
   establish successful login or authenticated API acceptance.

## Trusted deployment evidence

Generate an initially invalid template with:

```bash
python ci/deploy/staging.py template /private/staging-evidence.json
```

Fill it only from measured results. Every rehearsal flag is required, including
dump restores, reruns, injected failures, runtime tests, geography, ODK version
preservation, partner readiness and enabled hooks. Record per-image repository,
source commit, commit tag, digest and passing runtime test. Different accepted
source commits are supported for individual Registry images. Pin every image by
digest; no Registry or connector application image is rebuilt by staging promotion.

`deliveryHash` covers delivery code, chart, runtime checks, migrations and overlays.
`valuesHash` and `manifestHash` use `ci/deploy/staging.py:content_hash` over the
installed JSON values and parsed manifest list. `candidateManifestHash` uses
`manifest_hash` over the reviewed server-rendered candidate. It excludes revision
Jobs, whose execution is covered separately by hook rehearsal, and binds all
persistent resource bodies. Evidence expires after 24 hours; final maintenance
backups expire after one hour. A changed source tree or baseline requires review
and new evidence. An invalid template cannot authorize deployment.

Bind the reviewed file as Jenkins **Secret file** `staging-farmer-rehearsal`.
For optional coordination additionally bind:

- `staging-farmer-dev-services`: the accepted dev services deployment manifest.
- `staging-farmer-dev-acceptance`: digest-specific acceptance for both connector
  images and the coordinator's required checks. Its `staging` object contains
  `namespace: far`, the rehearsed `connectorChartHash`, and final connector
  snapshot `backupHash`. This authorizes a chart change with the same accepted images.
- `staging-farmer-connector-backup-directory`: a Secret text path to the verified
  final stopped connector snapshot on `vpn-agent2`, readable only by that agent.

No raw ODK or signing credential belongs in these evidence files. Use the supplied
ODK credential file only inside protected authentication/configuration handling.

## Farmer maintenance and Registry upgrade

1. Enter Farmer-only maintenance; pause Registry writers, refresh writers and
   legacy ingestion. Keep other registries and ODK collection available. Stop old
   connector processes with `release_handoff.py --environment staging pause-old
   --directory <new-private-directory>`. Verify no old pods/jobs or queued work
   can write. Take fresh final backups and hashes after stopping.
2. Apply exactly the rehearsed coordinate/document/application migrations. Record
   the final backup time, baseline revision/content hashes and completed cutover
   flags in the trusted evidence. Recheck current routing, resources and state.
3. Run the existing staging Jenkins branch with `DEPLOY_STAGING=true`. The shared
   RC helper promotes the tested image set, checks schema and resources, and waits
   for workloads and hooks. It never installs a missing Registry release. Staging
   uses no automatic Helm rollback across schema changes. Keep maintenance until
   schema, workload, route and reporting checks all pass.
4. Verify a fresh staff login, AWE statistics and task listing, then a uniquely
   identified synthetic web submission through the existing approval policy to
   Register. Record correlation IDs privately and aggregate outcomes publicly.

## Paused connector, manual acceptance and scheduling

1. Create the retained credential-only release using
   `helm/farmer-connector-credentials` and
   `helm/environments/staging/connector-credentials.yaml`. Create the isolated
   database and dedicated application role through protected PostgreSQL handling.
   Restore the complete final legacy dump into this database with ownership
   assigned to the new role; run the rehearsed application migrations there.
   Preserve failed runs as failed and copy only committed successes into successful
   idempotency state. Never manufacture keys from failed attempts.
2. Retain `farmer-partner` and register the dedicated staging public signing key.
   Preserve the appropriate project-1 ODK service account or provision one scoped
   to Farmer. Migrate the existing pipeline identity and mapping with both
   definitions paused; reconcile checkpoints and boundary IDs using the maintained
   recovery code. Record the final stopped-state evidence.
3. Set `COORDINATE_SERVICES=true` only after Registry acceptance. The connector is
   prepared with API/worker/UI replicas zero and beat/consumer disabled. Dashboard
   services resolve their `staging` branches. Missing branches/files preserve live
   services with an explicit skip; real failures make Jenkins unstable. Existing
   embedded dashboard API ownership and all unrelated resources must survive.
4. Use `release_handoff.py --environment staging start-replacement --acceptance
   <startup.json> --directory <new-private-directory>`. Startup evidence must name
   the current replacement `helmRevision` and prove paused pipelines, migrated
   mappings, reconciled checkpoints, drained old queue and registered signing key.
   Scheduler remains disabled. Run only the synthetic pipeline manually first.
5. Verify signed ODK ingestion, collector/Enumerator attribution, attachments,
   authorized approval to Register, retries and duplicate prevention. Reject
   wrong-issuer, unsigned, tampered, expired and wrong-key requests. Approve only
   synthetic records. Reconcile and ingest the existing real submission once,
   leaving it pending for its normal approver.
6. Pause pipelines and reconcile again. Supply staging acceptance with the current
   `helmRevision`, `snapshotHash`, `pipelinesPaused`, `checkpointReconciled`, and
   all pre-scheduler acceptance checks, then run `activate-scheduler`. The helper
   permits exactly one new beat using the worker's image, key and queue. Resume
   the intended pipeline and observe automatic polling without duplicate records
   or checkpoint regression.
7. Export then remove temporary acceptance records/accounts/media, retaining
   permanent identities and audit evidence. Fill all acceptance checks in
   `ci/deploy/staging.py:ACCEPTANCE`, including scheduler/polling/cleanup results.
   Bind accepted `images.api` and `images.ui` digests. Use `handoff-route`, record
   its new Helm revision, refresh acceptance for that revision, and only then use
   `connector_cutover.py --environment staging retire --directory <snapshot>
   --acceptance <acceptance.json>`. Retain the old DB, storage and backups.
   Where deployed, run dashboard health/reporting contracts before accepting it.

## Recovery and final evidence

On any failure, stop replacement ingestion and keep Farmer maintenance active.
Use a new private recovery directory; never overwrite the final backups or
handoff journal. Reconcile both databases' committed successes, source-event keys,
checkpoints and boundary IDs before choosing a restore/resume path. A Helm rollback
cannot reverse schema migrations. Do not resume unsigned legacy ingestion against
signature-enforcing intake. Test restoration and reconciliation in isolation
before restoring access.

Publish only credential-free source commits, digests, actual Helm revisions,
acceptance outcomes and recovery location references in the rollout manifest.
Keep dumps, raw manifests, ODK credentials, tokens, keys and submission data in
protected storage. Do not report any live criterion as passing until it was run.

The 16 October 2026 execution record records the
deployed revisions, tested image/configuration repairs, acceptance results,
remaining upstream defects and protected recovery locations. Consult it before
the next deployment; the retired legacy connector must remain stopped.
