# Farmer staging cutover, 16 October 2026

The RC.544 Registry is deployed in `far` at Helm revision 39. Jenkins staging
[build 14](https://jenkins.oanstaging.com/job/Gen2-Package/job/farmer-registry/job/staging/14/)
passed. The signed replacement connector is deployed at revision 4, with one
scheduler and the existing pipeline identity. Public maintenance has ended.

The source followed PR 105 into `develop` and PR 106 from `develop` to `staging`.
Deployed staging commit: `40e03c9a71e4c3c79c0d897a4f681901e8b75993`.
Merging source alone continues to default to `DEPLOY_STAGING=false`.

## Data and acceptance

The authorized reset retained the original database as
`farmer_registry_far_archive_20261016rc544`, with connections disabled. The
replacement was bootstrapped with application migrations and metadata only:
13 register definitions, 36 compatible coordinate columns and document-history
`event_type`. No CSV, packaged sample or forced population loader ran.

Fresh credential login, AWE statistics/listing, synthetic web approval and signed
ODK approval through both existing stages passed. Synthetic ODK collector
attribution, photo, land certificate and canonical Kebele were verified. All five
negative signature cases were blocked and created no intake records. Explicit
duplicate delivery returned the canonical run without another Registry request;
automatic polling preserved the timestamp/boundary checkpoint without duplicates.

Synthetic records, pipeline/history, ODK project, collector, intake user, temporary
AWE client and bootstrap Jobs were exported and removed. Shared AWE audit history
and protected acceptance evidence remain. The real ODK submission was ingested
once and remains pending its normal approver. The final business baseline is
**zero registered farmers and one pending real intake**. Seed population remains
deferred until Master Data is upgraded, as requested.

The dedicated ODK reader has `viewer` access to project 1 only; the supplied
administrative credential was used through protected tooling. `farmer-partner`
and its dedicated staging key remain. The replacement owns
`farmer_connector_v2_far` and queue `farmer-registry-connector-v2-far`. The legacy
connector was uninstalled with Helm history retained; `farmer_connector_far`
and its failed-run history/backups were retained.

Public Registry, connector and ODK URLs returned HTTP 200 without the maintenance
bypass. A fresh native approver OIDC session passed AWE reads after access was
restored. Connector `/health` returned `{"status":"ok"}` with a passing Postman
HTTP-status assertion. Reporting refresh passed before resuming its CronJob.

## Operational repairs

Build 13 failed while waiting for setup Jobs: their short TTL expired during an
ID Generator image pull. The official same-version Docker Hub ID Generator digest
was verified and pinned in the owning Helm values; setup Job TTLs were extended
to 3600 seconds. Guarded recovery reached revision 38; Jenkins build 14 then
repeated the deployment successfully at revision 39. The staging identity overlay
now records these exact tested settings for subsequent promotion through develop.

The disabled geography loader's chart still requires `master-data-db-user` in
`far`. Its required password key was copied from the existing Commons Secret into
the Farmer namespace without changing the shared Secret or enabling geography or
sample seeding. Keep this prerequisite until the owning chart removes the unused
requirement.

Accepted connector API/UI digests were promoted unchanged from dev revision 10.
The current coordinator wrapper computes a different image tag from that accepted
build. The paused install used the actual accepted tag/digests after runtime,
restored-database, namespace, queue, signing and manifest checks. The private
`connector/accepted-image-review.json` records this operator decision; the images
were neither rebuilt nor retagged and the wrapper artifact guard was not reported
as passing. Subsequent replica, scheduler, route and retirement actions used the
maintained environment guards.

The failed Commons upgrade left the Master Data API Service selecting no pods.
Only that Service selector was corrected to the existing deployment's labels.
No shared catalog rows, deployment images or broader Commons release were changed.
The before/after selector and recovery object are retained privately. The owning
Commons chart must reconcile this drift before its next upgrade.

The public connector Nginx configuration forwarded the public Host to a
VirtualService accepting the internal staging hostname. Its upstream Host is now
`connector-farmer-registry.far.staging.openg2p.test`; public TLS and forwarded host
remain `connector-farmer-registry.oanstaging.com`. The change is recorded with
before/after checksums in `connector/public-route-repair.json`.

## Known limitations

- An unsigned request is blocked with HTTP 500 rather than an authentication 4xx.
  Tampered, expired, wrong-key and wrong-issuer requests returned 401. Signature
  verification remains enabled; no invalid request created a record.
- The Registry Master Data hierarchy helper omits CSRF handling and its staging
  service credentials are incomplete. After repairing service routing it receives
  403. Canonical lowest-level IDs are preserved, but automatic hierarchy enrichment
  is incomplete. Correct the client and credential configuration through develop;
  do not disable Master Data authentication or CSRF protection.
- One Registry ingestion attempt hit an asynchronous database event-loop error.
  The normal retry succeeded on attempt 2 and created one pending intake. Keep
  this upstream worker defect visible in follow-up validation.

## Recovery locations

Protected staging host locations:

- `/var/backups/farmer-staging-20261016-cutover-preflight/`
- `/var/backups/farmer-staging-20261016-cutover-final/`
- `/var/lib/registry-coordination/farmer-staging-20261016-cutover/`

Full dumps were checksum verified and restored into isolated databases; a second
protected operator copy was verified. The journal contains exchange OIDs, original
Helm values/manifests, Nginx originals, migrations, accepted images, checkpoints,
ODK exports and acceptance evidence. It contains sensitive data and is not a
Jenkins or Git artifact. The credential-free rollout JSON records actual digests.

Stop replacement polling and reconcile committed successes/checkpoints before
recovery. Retain both databases. A Helm rollback cannot reverse the database
exchange or schema changes. Unsigned legacy ingestion must not resume against the
signature-enforcing intake.
