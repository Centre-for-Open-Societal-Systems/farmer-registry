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
- The local runbook is now [local/upstream](../local/upstream/README.md), with
  separate Commons Base, Commons Services and Registry Compose projects. This
  uses isolated volumes; it is not an existing-server data migration.
- Upstream GitHub checks are extended with COSS metadata, ODK transform, Compose,
  Helm and image-build checks. Six images, including the UI overlay, build
  without publishing. The inherited OpenG2P publisher is restricted to the
  upstream repository because its image destinations and secrets are upstream's.
- The old Jenkins deployment pipeline, vendored connector applications and
  private dashboard chart templates are removed from this registry layout.
  Existing deployed resources are not changed by this PR update. Their owners
  must manage connector/dashboard delivery separately; this chart is not a drop-in
  upgrade of the old combined release.

The existing PR history, including Suresh's merged #92, is retained. Its server
contract remains relevant: development uses `farmer-dev-kubeconfig`, registry
namespace `farmer` and shared namespace `commons`; staging remains separate.
The inherited generic chart does not encode that deployment's hostnames or
secrets. CI no longer automatically deploys this repository through Jenkins.

## Verified behavior

- Local live API suite: 11 passed, 2 skipped (ODK end-to-end and audit persistence).
- Browser acceptance: photo upload/replacement/removal and failed-upload
  preservation; COSS Region/Zone/Woreda/Kebele selection and readback; uppercase
  GC/EC; two distinct certificates with names, downloaded content, replacement,
  cancellation, failed-save preservation and removal with matching Yes/No flags.
- Browser draft approval through AWE: photo, Kebele and both certificate states
  remain intact after promotion into the registry.
- PR integration checks: RC pins and effective metadata (21 tests, 55 subtests),
  26 domain regressions in the pinned runtime, ODK transform rendering, Compose
  validation, and Helm lint/render.

ODK is mapped to the same Farmer intake approval policy, but the old patched
stack's passing ODK result does not establish end-to-end behavior on this RC
adoption. Do not copy the previous PR's 13/13 claim into this version's evidence.

## Deployment work before rollout

Configure COSS image/chart publishing, then supply those built image repositories
and tags for every Farmer component, including `registry.staffUi.image`. Chart
defaults use upstream image names and placeholder tags; they are not published
COSS artifacts. The COSS CI builds images but does not publish or deploy them.

Review a migration from the existing combined Helm release before upgrading it:
removing connector/dashboard templates from a release can remove its old resources.
Preserve live browser/auth configuration and namespace-local secret references.
Analytics is inherited from upstream and has only been rendered, not validated
against COSS production data. The four-level geographic override is currently
implemented in the local Commons Services seed; it is not an automatic server job.

The read-only [connector diagnosis](gen2-connector-diagnosis.md),
[seed diagnosis](gen2-db-seed-diagnosis.md) and `ci/gen2/` preflight/schema tools
are retained from #91 as operator references. PM issuer/partner onboarding,
coordinate and document-history schema prerequisites, and existing seed-data
repair remain server operations. No SSH writes, deployments, connector replays
or production data migrations were performed for this adoption.

PR #91 remains the single Farmer PR for this change. It is not merged by the
update, and no additional PR is needed for the adopted repository implementation.
