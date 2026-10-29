# Merge Farmer changes through develop into staging

This change is prepared for source review and promotion through **feature branch → develop → staging**. Merging source does not complete the staging database migration or signed-connector cutover.

## Merge sequence

1. Review and merge [PR #102](https://github.com/Centre-for-Open-Societal-Systems/farmer-registry/pull/102) into `develop`. Confirm the final head's checks pass. Preserve the included staging merge history: use **Create a merge commit** for this migration rather than squashing or rebasing away that ancestry.
2. Wait for the existing [Farmer Jenkins develop build](https://jenkins.oanstaging.com/job/Gen2-Package/job/farmer-registry/job/develop/) to finish. Develop automatically builds and deploys Registry to the dev environment, namespace `farmer`. A Registry failure stops the build; a genuine optional-service failure marks it unstable and needs investigation. Confirm the resulting release, login and normal Registry use before promoting that accepted develop commit.
3. Open the [develop-to-staging comparison](https://github.com/Centre-for-Open-Societal-Systems/farmer-registry/compare/staging...develop) after develop is merged. Create the promotion PR with base `staging` and head `develop`. The PR check rejects a different source branch. Wait for its checks, then merge it.
4. The [Farmer Jenkins staging build](https://jenkins.oanstaging.com/job/Gen2-Package/job/farmer-registry/job/staging/) validates with `DEPLOY_STAGING=false` and `COORDINATE_SERVICES=false` by default. A normal merge leaves the running staging Registry and connector intact.
5. Deploy staging only by completing the [staging upgrade runbook](staging-upgrade.md), providing fresh protected rehearsal/final-backup evidence and explicitly selecting `DEPLOY_STAGING=true`. Deployment must stop if any cutover prerequisite is unverified. Accepted connector images are promoted by digest, without rebuilding.

Remote `develop` and `staging` were refreshed on 16 October 2026. Both were ancestors of the reviewed migration branch, so neither branch's history required a new conflict resolution at that check. Recheck if another change lands before merging.

## ODK target retained

Public staging continues to use the separate Central server at [odk-central.oanstaging.com](https://odk-central.oanstaging.com), project `1`, form `farmer_profile`, on VM `odk-vm-2` (`16.4.11.90`). Do not replace it with `odk.commons.staging.openg2p.test`, which is a different Kubernetes installation. Further staging ODK server changes are deferred; this Farmer merge does not deploy Commons or the Central VM. The dev environment now uses [odk-central-development.oanstaging.com](https://odk-central-development.oanstaging.com), with the former Commons address retained as an alias; see the [hostname migration](odk-dev-hostname.md).

The existing map correction and form `1.0.5` were rechecked on the public staging VM. Chrome and Firefox rendered all visible tiles and saved a clicked point. The canonical Kebele dropdown and parent-change clearing passed. Its existing submission XML and attachment were preserved. See [map configuration and recovery](odk-map-tiles.md).

## Why the UI shows 20 farmers

The deployed dev register page requests `page_size: 20`. That is the number of results on one page, not the database total. Read-only aggregate queries on 16 October 2026 found:

| Environment | Registry database | Registered farmers | Tagged `created_by = seeder` | Other registered farmers | Farmer intake rows |
| --- | --- | ---: | ---: | ---: | ---: |
| Dev | `farmer_registry` | 27 | 21 | 6 | 10 |
| Staging | `farmer_registry_far` | 1,000,501 | 500 | 1,000,001 | 32 |

The staging 500-row seed remains present. The remaining staging rows are reported only as an aggregate; their origin was not classified by this check. Intake and history are separate tables and are excluded from registered-farmer totals.

Sample farmers come only from the ETH-OAN country pack in openg2p-data. The db-seed image's sample loader reads them from Master Data and the pack and enters each one as a farmer intake approved at both stages (off on every environment); nothing in this repository is a sample population source.

Deployment preparation disables geography, sample, image and bulk fixture loading on every environment. This merge does not reload 500 people, truncate a register or reconcile existing Farmer locations. Expanding the dev demo population is a separate explicit data operation, with canonical geography and duplicate handling, rather than an automatic deployment hook.

## Staging deployment prerequisites still outstanding

- Reconcile the existing Farmer records carrying fictitious Kamuntu selections. The shared catalog repair is complete; the remaining record changes have a separately rehearsed proposal and have not been applied.
- Complete staging `farmer-partner` registration, dedicated signing-key setup and the enabled external-hook rehearsals.
- Perform Farmer maintenance, fresh final backups, the rehearsed schema/application migrations and live Registry acceptance. Staging still has Registry revision 36 and legacy connector revision 3 at this inspection.
- Verify synthetic signed ingestion and approval, the real-submission reconciliation and single-scheduler acceptance before retiring legacy ingestion.

These prerequisites remain enforced. Do not mark their evidence fields true merely to run the deployment. Source merge readiness does not establish end-to-end staging readiness.

## Verification for merge review

- Both current Jenkins environment definitions passed the deployed Jenkins declarative validator. The existing multibranch job uses `Jenkinsfile`; its develop and staging branches are enabled, and their last inspected builds succeeded.
- Refreshed Linux validation passed 493 unit tests and 109 subtests; the four Helm credential tests passed separately, for 497 distinct passing unit cases. One staff-UI asset case remains skipped. Deployment shell success/failure/recovery cases, staging evidence sequencing, environment contracts, ODK transform and links in 44 documentation files passed. The staging shell harness also passed on Bash 4.3.
- Fresh server-side candidate renders against dev revision 26 and staging revision 36 passed Helm lint and resource/configuration preservation. The dev environment's live schema gate passed. Staging's read-only schema gate correctly rejected all 36 unconverted coordinate columns. No release, schema or business data was changed by these previews.
- GitHub checks on the final PR head remain the merge gate. The promotion PR must also pass its own checks after the develop merge.

The rollout manifest records the rehearsal results, image identities, live outcomes and remaining blockers. Private dumps, Helm values, raw submissions and credentials remain in protected operator storage.
