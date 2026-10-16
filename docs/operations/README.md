# Dev and staging delivery

The existing `Gen2-Package/farmer-registry` multibranch Jenkins job is the maintained
entrypoint, with script path `Jenkinsfile`. Separate worker-auth, signing and
services-dev jobs are no longer required. Discover `develop` and `staging`;
pull requests validate without publishing or deploying.

| Setting | Dev | Staging |
| --- | --- | --- |
| Source branch | `develop` | `staging` |
| Pipeline | `ci/pipelines/dev.groovy` | `ci/pipelines/staging.groovy` |
| Namespace | `farmer` | `far` |
| Registry release | `farmer-registry` | `farmer-registry` |
| Connector release | `farmer-registry-connector` | `farmer-connector` until accepted cutover to `farmer-registry-connector` |
| Kubeconfig credential | `farmer-dev-kubeconfig` | `staging-farmer-kubeconfig` |
| Staff issuer | `https://keycloak-development.oanstaging.com/realms/staff` | `https://keycloak.oanstaging.com/realms/staff` |
| Registry UI | `https://farmer-registry-development.oanstaging.com` | `https://farmer-registry.oanstaging.com` |
| Platform | `1.2.2-rc.544` | `1.2.2-rc.544` candidate; live upgrade pending |

## Dev

Use the [develop-to-staging merge handoff](merge-develop-staging.md) for the migration PR, promotion sequence, seeded-farmer counts and remaining staging cutover gates.

Merged develop builds validate, build six Registry images, publish commit-tagged
images, and upgrade the existing release. Registry failures are fatal. Available
Farmer add-ons release independently; their failures mark Jenkins unstable.
Missing branches or application files preserve existing deployments.

The deployment agent is `vpn-agent2`. Build agents need Docker, Bash, Git and AWS
CLI. Helpers provide Python dependencies in containers. Publishing uses
`aws-ecr-creds`; protected backup transfer uses `farmer-new-dev-backup-ssh`.
Identity migration additionally requires explicit `APPLY_COMMONS_IDENTITY` and
fresh `farmer-dev-identity-evidence`.

`ci/deploy/deploy-dev.sh` requires an existing release, validates schema and
resource preservation, uses the committed chart lock, and keeps private values
out of artifacts. A failed release requires guarded recovery, never deletion.

## Staging

Read-only SSH inspection reached `52.66.116.220` through the Jenkins VPN agent.
Its RKE2 kubeconfig is `/etc/rancher/rke2/rke2.yaml`. Farmer runs in `far`.

The RC candidate uses the shared `ci/deploy/deploy-rc.sh` helper.
`DEPLOY_STAGING` defaults to false. Promotion requires protected, fresh rehearsal
and final maintenance backup evidence. Registry and connector application images
retain their tested digests. Legacy helpers remain as historical source;
the maintained pipeline no longer invokes them.

Follow the [staging upgrade and signed ODK runbook](staging-upgrade.md). It covers
isolated restores and hook rehearsals, Farmer maintenance, paused connector
preparation, manual synthetic approval, real-submission reconciliation, scheduler
activation, retirement and recovery. Live staging remains unchanged until those
steps actually run.

Inspection found `commons-services` revision 12 in Helm state `failed`, while
inspected service deployments were ready. Its recovery belongs to the Commons
owner. Inspected Registry values contained an internal Keycloak issuer URL while
OIDC discovery advertised the public staff issuer. The candidate staging overlay
uses that public staff issuer; effective authentication and negative signature
cases still require live acceptance.

## Shared maintenance

Retain the separate `farmer-registry-commons-services` job and its credentials.
Its configured `ci/commons-services/Jenkinsfile` is absent from current upstream
`develop`; do not run it until its owner restores the source. Farmer cleanup does
not grant permission to upgrade shared Commons services.

See [service coordination](coordinated-services-rollout.md),
[connector recovery](connector.md), and the [cleanup inventory](cleanup-inventory.md).
