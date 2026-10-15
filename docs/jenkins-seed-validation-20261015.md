# Jenkins and seed recovery validation — 2026-10-15

Build 5 passed release, schema, candidate and revision checks, but stopped before
Helm upgrade on an empty-array expansion under older Bash. The deployment script
now keeps readiness arguments in a nonempty array and adds atomic rollback only
for normal upgrades. Its actual control flow is exercised with fake tools on
Bash 4.3 and 5.2, covering normal/recovery success and failure. This proves shell
behavior, not a live Helm upgrade.

The deeper rehearsal found that the inherited seed used `ON_ERROR_STOP=0`, ran
shared lookup SQL against Registry, and included baseline inserts that failed on
duplicates. The COSS entrypoint now uses database transactions and propagates
errors. Shared lookup catalogs are excluded; seven baseline inserts use
`ON CONFLICT DO NOTHING`. Existing explicit COSS upserts remain in effect.

## Executed checks

- Built the actual db-seed Dockerfile with the new entrypoint.
- Seeded an isolated clone of the repaired dev Registry database, then ran the
  complete seed twice with an isolated AWE database and local MinIO bucket.
  Both complete runs exited zero and uploaded all four templates.
- Compared counts and full-row checksums across 32 business tables against the
  source database: all unchanged, including intake, register and history records.
- Injected an invalid SQL statement after a table creation in the same metadata
  batch: the error propagated and the preceding creation rolled back. Comment-only
  placeholders and duplicate reruns also passed. CI runs these against PostgreSQL.
- Ran the same entrypoint against the local application stack, including AWE,
  geo-widget synchronization and template uploads: exited zero.
- After seeding, the local live API suite passed 11 tests including intake
  save/readback/approval, DCI, negative authorization and change requests.
  Two tests were skipped: ODK submission/approval and audit persistence.
- Ran the actual sanity-image entrypoint with deployment settings: 3 smoke tests
  passed, 11 non-smoke tests deselected.
- Verified the local checksum-ledger migration accepts only the exact addition
  of duplicate-safe baseline behavior; other applied SQL changes still fail.
- Python regression checks passed 185 tests and 57 subtests locally, with two
  environment-dependent tests skipped.
- The final container regression suite passed 187 tests and 57 subtests. After
  adding Helm diagnostics, all 39 deployment-guard tests passed.
- Split the rendered candidate into ordinary manifests and Helm hooks, then
  rejoined them with the same YAML separator as the deployment script. Validation
  found all seven required workloads, including db-seed and sanity hook Jobs.
- The actual shell harness verifies that a failed upgrade invokes diagnostics
  and stops before post-upgrade hook validation. Failure summaries classify hook
  retries, timeouts, image pulls, authorization and resource-update errors without
  echoing private Helm output. Unknown errors are explicitly reported as such.

## Limits and live-server state

Server inspection was read-only. Revision 5 remained failed; its seed Job has no
remaining pod logs, so the precise historical exception cannot be recovered.
The live schema gate passed, and the candidate preserved the current release's
resources/configuration. No Helm upgrade or seed was run on new dev during this
validation. A successful merged Jenkins deployment is still required to establish
server recovery. PM onboarding, ODK publication and live ODK approval remain
separate unverified steps; the passing local API tests do not establish them.

Seed transactions are per database. If AWE or object upload fails after Registry
commits, the job fails but does not undo the earlier commit. The idempotent rerun
path is tested; database backups remain necessary before operator migrations.
