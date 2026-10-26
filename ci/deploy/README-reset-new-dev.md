# One-time New Dev reset helper

`reset_new_dev.py` is a guarded helper used by `new-dev-reset.sh`. No invocation during import;
default CLI mode validates and prints a plan fingerprint only. The example is
disabled and intentionally has unreviewed placeholders. Do not use it as a live
manifest. The deployment owner supplies the discovered exact cluster UID,
namespace/release, DB address/port/name/owner, pinned image digests, workload
names and reviewed native snapshot/migrate/seed/verify commands.

Execute only in Linux CI using the approved deployment context and mounted
libpq service/password files. `--execute --initialize-receipt --admin-service NAME`
explicitly initializes the first receipt. `--execute --resume --admin-service NAME`
resumes the same manifest. There is no automatic creation of a missing receipt
on resume, lock expiry, force overwrite, forced client termination or repeated
DROP after `RESET_STARTED`. A registry-stable namespace ConfigMap stores state,
manifest hash, target identity, backup hashes and original workload replicas.
`resourceVersion` protects every replace. A verified receipt skips execution;
changed epoch/manifest refuses rather than resetting again.

Ordinary New Dev deployments use `python3 ci/deploy/reset_new_dev.py
<immutable-first-install-manifest.json> --require-verified`. This read-only mode
validates the reviewed manifest, exact cluster/namespace and stable ConfigMap
receipt. It requires the same target, epoch, fingerprint, state VERIFIED and an
explicit empty lock. Missing/incomplete/drifted/locked receipts return nonzero.
It never constructs the DB/action adapter, connects to PostgreSQL, runs native
commands, scales workloads or creates/replaces receipts. No admin service is
required or accepted. Keep the original manifest/epoch unchanged for later
routine builds; new build image pins must not overwrite this reset manifest.
`--require-verified` cannot be combined with execute/initialize/resume flags.
Explicit reviewed first-install initialize/resume remains a separate pipeline
stage; a missing guard receipt never triggers a reset automatically.

Backups must be custom pg_dump archives in an existing owner-only directory.
Original replicas are saved durably and target writers are drained before the
archive is taken; a failure here leaves the target paused for explicit recovery.
Archive listing and actual restore into an owned disposable database must pass.
The snapshot command must write `<epoch>.snapshot.json` there with mode 0600,
preserving release configuration, document references and connector checkpoints.
Do not include credentials in that file or receipts. The helper checks its hash.
Native commands receive target/epoch/private directory via environment variables;
their implementation and immutable image selection require pipeline review.
They must not delete buckets, queues, checkpoints or shared Commons resources.

Only exact listed deployment/statefulset workloads carrying the selected Helm
release label are scaled. Both zero replicas and zero DB clients are required.
Only controlled verification replicas are restored for acceptance. Failure after reset intent
pauses the target. On interrupted `RESET_STARTED`, an absent DB may be created;
an existing DB is ambiguous and requires operator recovery, never another DROP.
Confirm an interrupted lock owner is stopped before reviewed recovery unlocks it.
Keep the outer Jenkins environment lock as an additional control.

Required tools: kubectl, PostgreSQL client tools, Python and psycopg2. Child
output and exceptions are not echoed because they may contain secrets. Protected
pipeline diagnostics must supply operational error details. Tests use fake CAS,
workloads and DB operations; real cluster/restore rehearsal remains a release
gate. Run `uv run --no-project --with pytest pytest -q tests/unit/test_reset_new_dev.py`.

Only `verification_workloads` (a required proper subset of the exact target
workloads, normally Staff API/dashboard) are restored for controlled acceptance.
Partner APIs, beat and workers must remain outside this subset. Verification
success persists `ACCEPTED`; only then are remaining replicas and external
producers restored. An interrupted restoration resumes from `ACCEPTED` without
repeating the DROP or native verification. Failures pause producers and target
workloads again. Each reviewed pause/assert/resume command must be idempotent
and preserve checkpoints/queued events.

Before wiring: inventory and pause any target HPA, CronJob, external connector or
other producer outside the listed workloads. The read-only controller preflight
refuses any target HPA, unsuspended target CronJob or active target Job, including
an unlabeled HPA pointing at a target workload. It never deletes controllers or
patches schedule suspension automatically. `pause_producers`,
`assert_producers_paused` and `resume_producers` are mandatory reviewed native
commands. The pause assertion runs before backup/drain and again before reset;
passing evidence is recorded in the receipt. Resources managed outside the
release require the external assertion, even when their labels cannot be found
by this helper. Exact Deployments/StatefulSets and zero DB clients are still
required, not a substitute for the external contract.
Provide real target manifests and native command implementations, test ConfigMap
RBAC/CAS against an owned rehearsal namespace, and complete fresh-install/live
acceptance. The example and unit checks do not establish deployment readiness.


The deployment wrapper defaults to `NEW_DEV_RESET_ACTION=check`. Bind
`REGISTRY_RESET_MANIFEST` to the immutable first-install JSON. It refuses this
repository's current `promotionReady=false` profile before Kubernetes access.
Only explicit `initialize` or `resume` selects execution, requires the verified
build source and exact `name:version@sha256:digest` chart lock to match the
manifest, and needs `REGISTRY_RESET_ADMIN_SERVICE` plus mounted libpq files.
These are deployment-node configuration, never committed credentials. Native
commands, service accounts, producer/controller pauses and protected artifact
storage must be provisioned and rehearsed before changing promotion readiness.
The example remains disabled. No ordinary build automatically initializes a
missing receipt. After the first rebuild, return the pipeline action to `check`.
