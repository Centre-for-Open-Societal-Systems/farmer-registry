# Farmer first: source publication and preserving adoption

The first rollout includes only the core Farmer registry. Crop, Livestock,
Commons, existing connectors and independent dashboards retain their releases.
Staging is outside this rollout.

The source dependencies are central `oan-helm` PR #14 into `main`, then Farmer
PR #124 into `develop`. Both were merged on 27 October 2026. Farmer Jenkins
build #30 published all six images for merge commit
`431cbdaf63a06fbf60cb436784f4815794d153a8`, then failed at the promotion guard
before upgrading Farmer. This publishes reviewed chart/source; it is not
application acceptance. Do not merge receiving registry or standalone dashboard
PRs for this step.

With this follow-up, the existing `Gen2-Package/farmer-registry/develop` job defaults to
`NEW_DEV_DELIVERY_ACTION=publish-only`, including the first automatic build
before Jenkins has installed the new parameter definitions. It builds/tests the
six images and publishes their actual checked-out commit tag and ECR digests.
The native Celery SAVE/parent/finance/rollback probe runs against that exact
image in an owned disposable PostgreSQL. Jenkins retains its artifacts.
`service-outcomes/publication.json` records publication separately from deployment.
All cluster deployment and optional-service stages require explicit `deploy`.
`COORDINATE_SERVICES` defaults to `false`.

Publication never supplies a reset receipt, changes the chart promotion gate,
or upgrades a live release. The pinned chart still blocks workload rendering;
`promotionReady=false` and the existing database/adoption guards remain active.
Selecting `deploy` cannot bypass them.

After publication, bind the actual merged source and all six image digests to
the preserving-adoption rehearsal. A live upgrade requires a fresh coordinated
database/filestore/configuration backup, restored-copy native migration and seed
verification, reviewed rendering against the current release, and the preserving
upgrade path. Prior snapshots taken while writers were active are rehearsal
inputs, not a current coherent cutover backup. Do not use `initialize`/`resume`
or drop/recreate the existing New Dev database to satisfy the first-install gate.
Preserve history, documents, pending approvals, identity assignments, connector
checkpoints and environment settings.

The preserving follow-up uses a separate immutable `adoption-chart.json` so
legacy/optional delivery pins remain unchanged. The consolidated central Helm
review is PR16 (dev.16). `adoption-candidate.json` freezes the already published
and rehearsed Jenkins31 application images at afdbf75, independently of the
later delivery-controller commit. A runtime-source hash refuses changes to the
extension/image/UI inputs after that rehearsal.

Use `preserve-preflight` first, then `preserve-upgrade`, through the same Jenkins
develop job and existing `farmer-new-dev-backup-ssh` credential. Both modes reject
any reset selection. Preflight only reads the live release and verifies a private
diagnostic render. Upgrade saves exact workload UIDs/replicas and schedules,
pauses Farmer writers, takes native restored backups and a protected filestore
copy, runs the native migration/seed/reporting Jobs, verifies original business
values, then creates the expiring native-ready receipt for the real chart.

The actual Helm upgrade retains persistent resources and suppresses fresh
database/realm initialization. Native Jobs execute explicitly under the same
receipt. APIs/UI start before producers. Read-only native smoke and HTTP
readiness must pass before restoring the original worker/connector replicas and
schedules. An interrupted operation retains its private directory and requires
explicit recovery; it never drops a live database or rolls old images back
across schema changes. Shared Commons services remain online for other
registries, so their archive snapshots are not advertised as a globally frozen
cross-service cutover.

Source and restored-copy approval metadata now use the standard OpenG2P
two-stage defaults; geographic/custom reviewers are deferred. Existing AWE
tasks keep their policy and assignees. Live default reviewer resolution and
final approval decisions remain application acceptance checks after adoption.
