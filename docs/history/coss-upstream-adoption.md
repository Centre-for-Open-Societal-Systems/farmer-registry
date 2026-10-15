> Historical evidence. Use [current operations](../operations/README.md) for maintenance; recorded commands and job links describe past rollouts.

# COSS adoption of the upstream Farmer RC architecture

PR #91 adopts the OpenG2P Farmer repository layout at
`5babaca7d513cf94a7cc6f366b19964f2c021913` and pins runtime images and the registry
chart dependency to **1.2.2-rc.544**. The layout commit is not an RC release tag.
Commons Base **2.3.3** and Commons Services **2.3.4-rc.245** remain independently
managed. COSS owns its farmer domain package, metadata, translations, ODK mapping
and the small guarded staff UI overlay. There is no separate frontend source fork.

## What changes from the previous PR implementation

- Per-component Dockerfiles replace the root multistage Dockerfile and the
  general backend patch script. Published RC components provide the platform.
- The upstream Helm wrapper replaces the expanded COSS chart. The staff UI image
  override explicitly includes the COSS photo/certificate/calendar-label fixes.
- Agent Portal/credential-issuance settings from the newer upstream layout are
  excluded: no agent-portal-api image exists at rc.544.
- The local runbook is now [local/upstream](../development/local-stack.md), with
  separate Commons Base, Commons Services and Registry Compose projects. This
  uses isolated volumes; it is not an existing-server data migration.
- Upstream GitHub checks are extended with COSS metadata, ODK transform, Compose,
  Helm and image-build checks. Six images, including the UI overlay, build
  without publishing. The inherited publisher is retained at
  `ci/upstream/build-publish.yml.example` for adapting COSS release automation;
  its destinations and secrets belong to upstream, and GitHub rejects the
  inherited reusable workflow before starting jobs in this fork.
- The old combined Jenkins pipeline was removed during adoption. The replacement
  [new-dev Jenkins pipeline](../operations/README.md) builds the six RC-based
  images and upgrades the existing Registry release on merged `develop` builds.
  The optional dashboard template preserves its existing Helm ownership and image.
  The connector remains an independently managed release.

The server contract from Suresh's merged #92 is retained: development uses
`farmer-dev-kubeconfig`, registry namespace `farmer` and shared namespace
`commons`. Staging remains separate and is not deployed by this pipeline.
Existing release values supply the deployment's hostnames and secret references.

## Verified behavior

- Local live API suite: 11 passed, 2 skipped (ODK end-to-end and audit persistence).
- Browser acceptance: photo upload/replacement/removal and failed-upload
  preservation; COSS Region/Zone/Woreda/Kebele selection and readback; uppercase
  GC/EC; two distinct certificates with names, downloaded content, replacement,
  cancellation, failed-save preservation and removal with matching Yes/No flags.
- Family Size is hidden in Farmer and Household intake metadata. The domain
  service calculates male + female totals; children and parents are not added
  again. Browser save/edit/reopen verifies totals of 5 and 6. A separate seed
  migration preserves the checksums of previously applied metadata.
- Browser draft approval through AWE: photo, Kebele and both certificate states
  remain intact after promotion into the registry.
- PR integration checks: RC pins and effective metadata (22 tests, 57 subtests),
  35 domain regressions in the pinned runtime, ODK transform rendering, Compose
  validation, and Helm lint/render.

ODK is mapped to the same Farmer intake approval policy, but the old patched
stack's passing ODK result does not establish end-to-end behavior on this RC
adoption. Do not copy the previous PR's 13/13 claim into this version's evidence.

Performance-testing files remain identical to the PR base; this change adds no
performance tests or performance CI jobs.

The earlier 2026-10-15 read-only SSH recheck confirms that dev ODK downloads succeed but
registry still rejects the unregistered partner. PM issuer configuration and
schema prerequisites remain unresolved; the Farmer AWE policy is configured.
See the dated [connector evidence](gen2-connector-diagnosis.md#read-only-recheck-2026-10-15-0335-0336-utc).

Subsequent operator work completed the coordinate/document-history repairs;
the continuation reverified all 36 coordinate columns, document `event_type`,
workload recovery and the separate `farmer-connector` Helm owner. After explicit
shared-catalog approval, dev geography was migrated to COSS/ODK: 346 references
were mapped and 509 legacy land references preserved. Form publication and live
ODK approval remain pending. See the
[current geography rollout and handoff](../history/odk-geography-20261015.md) for aggregate
evidence, checks, backups and remaining rollout steps. The earlier
read-only diagnosis is historical, not the current schema state.

## Deployment work before rollout

Follow the [Jenkins setup and deployment guide](../operations/README.md).
GitHub checks validate and build without publishing; Jenkins publishes commit
images and upgrades new dev after merge to `develop`. Chart defaults still use
placeholder tags and must not be installed directly onto the existing server.
The migration guard compares the candidate against the live release before any
upgrade and preserves the dashboard, routing and environment references.

Analytics has only been rendered, not validated against COSS production data.
The pipeline disables demo/geography seeding and does not perform shared catalog
migrations. PM configuration, partner onboarding and ODK form publication remain
separate rollout steps.

The read-only [connector diagnosis](gen2-connector-diagnosis.md),
[seed diagnosis](gen2-db-seed-diagnosis.md) and `scripts/operations/commons/` preflight/schema tools
are retained from #91 as operator references. PM issuer/partner onboarding,
coordinate and document-history schema prerequisites, and existing seed-data
repair remain separately managed server operations. The initial architecture
adoption itself performed no server writes; later dev schema and approved shared
geography migrations are recorded in the continuation linked above. No connector
replay or ODK publication is established by the architecture adoption.

PR #91 remains the single Farmer PR for this change. It is not merged by the
update, and no additional PR is needed for the adopted repository implementation.

The [PM rollout package](pm-issuer-and-approval-rollout.md) supplies a separately
owned Commons overlay for the verified issuer, PM/IAM route collision and logout
issues, with a manifest guard and local PM 1.0.2 lifecycle checks. It does not
deploy Commons or activate the server connector partner from Farmer CI.
