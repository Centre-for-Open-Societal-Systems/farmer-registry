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
| Connector release | `farmer-registry-connector` | `farmer-connector` |
| Kubeconfig credential | `farmer-dev-kubeconfig` | `staging-farmer-kubeconfig` |
| Staff issuer | `https://keycloak-development.oanstaging.com/realms/staff` | `https://keycloak.oanstaging.com/realms/staff` |
| Registry UI | `https://farmer-registry-development.oanstaging.com` | `https://farmer-registry.oanstaging.com` |
| Platform | `1.2.2-rc.544` | `0.0.0-develop.384` legacy |

## Dev

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

The legacy deployment implementation is retained in `ci/deploy/staging-legacy.sh`
and its build path in `ci/build/staging-legacy.sh`. `DEPLOY_STAGING` defaults to
false. Enabling it requires the staging branch, legacy root Dockerfile and
matching legacy chart. The rc.544 dev layout deliberately fails that preflight;
porting staging to the newer platform requires a separately reviewed migration.
A cleanup merge into develop does not change the staging branch or deploy it.

The staging path requires its existing deployed release and expected hostname;
it never installs chart defaults. It preserves current environment values and
does not deploy, activate, replace or remove the staging connector.

Inspection found `commons-services` revision 12 in Helm state `failed`, while
inspected service deployments were ready. Its recovery belongs to the Commons
owner. Registry values also contain an internal Keycloak issuer URL while OIDC
discovery advertises the public staff issuer; review effective authentication
separately before accepting any identity migration. Cleanup does not repair either.

## Shared maintenance

Retain the separate `farmer-registry-commons-services` job and its credentials.
Verify its configured script against the owning repository before use. Farmer
cleanup does not grant permission to upgrade shared Commons services.

See [service coordination](coordinated-services-rollout.md),
[connector recovery](connector.md), and the [cleanup inventory](cleanup-inventory.md).
