# Reset Farmer staging and deploy the RC

This is an explicit test-environment operation, separate from ordinary delivery.
All source changes follow **feature → develop → staging**. The user chose to
reset only Farmer Registry and, after discovering staging Master Data lacks a
sample API, to **leave the register empty until Master Data is upgraded**.
Run `db_seed` metadata only. Do not load packaged samples, the old CSV fixtures,
images or bulk data. Shared Commons and its geography, identity accounts, other
registries and the separate staging ODK server/submissions remain intact.

Staging build 11 validated merge `73a792361568bccb2b258b251aa90bdde7dae171`;
it skipped deployment. Registry revision 36 still served October 8 images when
inspected. A validation-only Jenkins build now says so in its description and
console. Its success does not establish a deployment.

## Rehearse before maintenance

The operator entrypoint is `scripts/operations/staging/reset_registry.py`.
It uses the existing staging kubeconfig, PostgreSQL pod and Secret references.
Use a promoted staging checkout on the trusted staging host, with Python/PyYAML,
Git, Helm and kubectl. Keep the working tree clean and fetch COSS develop and
staging objects first. `create` and `exchange` verify the remote COSS staging
head and require the implementation commit in **both** develop and staging.

1. Resolve the accepted develop image set and record per-component source commits,
   tags and digests. Do not rebuild images in staging. Refresh the standard
   [upgrade rehearsal](staging-upgrade.md), including isolated dump restores,
   every enabled hook, partner/signing-key readiness, issuer and signature tests.
2. Run `python tests/runtime/test_staging_reset_database.py` on a Docker host.
   It tests database grants/settings, atomic exchange, repeated invocation,
   injected failure, recovery and preservation of an unrelated database.
3. Run the empty bootstrap against the exact accepted images:

   ```bash
   python tests/runtime/test_staging_reset_bootstrap.py \
     --api-image "$ACCEPTED_API_IMAGE" --seed-image "$ACCEPTED_SEED_IMAGE" \
     --directory /private/farmer-reset-bootstrap-<run>
   ```

   This uses a disposable PostgreSQL 16 instance on an internal-only Docker
   network. It creates `pg_trgm`, runs application migrations twice, prepares
   document history, runs metadata seeding twice, builds reporting and injects
   seed transaction failures. Require zero farmers/intakes and 36 compatible
   coordinate columns. External hooks are deliberately excluded here and need
   their own isolated rehearsal before live deployment.

## Prepare a candidate without replacing live data

Choose a unique 8–16 character lowercase alphanumeric reset ID. Every directory
and database name is single-use; do not overwrite an earlier journal.

```bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
export KUBECONFIG_CREDENTIAL=staging-farmer-kubeconfig
python scripts/operations/staging/reset_registry.py inventory \
  --reset-id "$RESET_ID" --directory "$RESET_DIRECTORY"
```

The private directory receives `plan.json` and an invalid evidence template.
Set only the reviewed reset authorization and measured source provenance in a
separate protected evidence file. `sourceCommit` must be the current COSS staging
head; `implementationCommit` must contain this reset implementation and already
belong to develop and staging. Retain the generated `deliveryHash`.

```bash
python scripts/operations/staging/reset_registry.py create \
  --directory "$RESET_DIRECTORY" --evidence "$RESET_EVIDENCE"
```

This creates `farmer_registry_far_reset_<id>`, copying the original database's
owner, encoding, locale, tablespace, connection limit, effective ACL and per-role
settings, and installs `pg_trgm`. It does not replace the live database.

Render the normal reviewed RC candidate manifest through the existing Helm
preservation checks. Supply that protected manifest and a private JSON object
with `staff-api` and `db-seed` image references in `repository:commit@sha256` form:

```bash
python scripts/operations/staging/reset_registry.py render-jobs \
  --directory "$RESET_DIRECTORY" --manifest "$CANDIDATE_MANIFEST" \
  --images "$ACCEPTED_RESET_IMAGES"
```

Run the generated `migrate.json` Job to completion, then `metadata.json`, one at
a time in `far`. Keep their logs private. The Jobs target only the reset
candidate and retain existing Registry Secret references. They receive no
shared-database credentials; shared AWE seeding, geography, templates, sample and
image loading are disabled. The migration Job uses the accepted API's normal
`python3 -m openg2p_registry_staff_api.main migrate` command.

Apply the document-history SQL to the candidate with protected PostgreSQL
administration, as rehearsed. Verify all application tables and metadata, then:

```bash
python scripts/operations/staging/reset_registry.py seal \
  --directory "$RESET_DIRECTORY"
```

Sealing requires compatible schema, an empty business register and identical
database permissions/settings. It records candidate OID, every public table's
row fingerprint and schema/index/constraint definitions. Subsequent drift blocks
exchange. Repeated preparation requires a new reset ID rather than reseeding.

## Maintenance, exchange and deployment

Enter the first ready Farmer-only maintenance window after all rehearsals pass.
Block every Farmer intake/approval route and internal callback writer, including
stale pre-reset AWE tasks; retain shared AWE history and other registries' work.
Stop Farmer API/worker/beat and legacy connector processes, suspend Farmer
CronJobs, finish/stop active Jobs and drain Farmer queues. Capture replica and
route state for recovery. Keep ODK collection available.

Take fresh final Registry/connector dumps after stopping writers. Retain checksums,
verified durable copies, Helm values/manifests, ODK form/media, mappings, failures,
idempotency/checkpoint state and workflow evidence. In the reset evidence file:

- Set `planHash` and `sealedHash` to the SHA-256 of the reviewed private files.
- Record final dump paths and SHA-256 values in `backups.registry` and
  `backups.connector`; refresh `verifiedAt` and `finalBackupAt` from actual work.
- Mark each `checks` field true only with measured evidence. Evidence must be
  within 24 hours and final backups within one hour. The file contains no keys
  or passwords and must never be a Jenkins artifact.

```bash
python scripts/operations/staging/reset_registry.py exchange \
  --directory "$RESET_DIRECTORY" --evidence "$RESET_EVIDENCE"
```

The tool rechecks provenance, baseline Helm revision, database identity/settings,
backup integrity, stopped workloads and the sealed candidate. It fences both
databases, terminates connections, and atomically renames the original to
`farmer_registry_far_archive_<id>` and the candidate to `farmer_registry_far`.
The archived database remains inaccessible and is **never dropped**. A failed
exchange leaves maintenance active and databases fenced for explicit recovery.

Complete the standard trusted staging deployment evidence with the measured
fresh-schema/reset results, then bind `staging-farmer-rehearsal`. Run Jenkins
with `DEPLOY_STAGING=true`, initially `COORDINATE_SERVICES=false`. The read-only
schema Job uses the accepted API image and DB Secret references, so API pods can
remain stopped until Helm upgrades them. Ordinary merge defaults remain false.

Follow [the signed cutover acceptance](staging-upgrade.md) for fresh login, AWE,
web approval, signed ODK, attachments, rejection cases and single-scheduler
acceptance. Preserve old connector history in its retained DB/archive. Do not
copy successful-ingestion markers for destination records removed by the reset;
reconcile source IDs against the new Registry and ingest preserved ODK
submissions once, leaving real records pending their normal approver.

Zero business records is the seed acceptance baseline. Synthetic acceptance and
preserved real ODK intake can add records afterward; report these separately.

## Recovery

Keep all writers stopped and reconcile queues/checkpoints before restoration.
If exchange failed, inspect the saved SQL and database OIDs; do not simply rerun
it or reopen connections. If restoring the original, first archive the new
database under a fresh name, then rename the retained original back, in one
transaction with both databases fenced. Re-enable connections only after the
original configuration is restored. Retain the replacement for investigation.
The PostgreSQL runtime rehearsal proves this exchange/recovery sequence.

Select compatible application images together with the restored schema. Helm
rollback alone cannot restore database state. Unsigned legacy ingestion must
remain stopped against signature-enforcing intake. Publish only actual commits,
image digests, Helm revisions, aggregate counts and protected recovery locations.
