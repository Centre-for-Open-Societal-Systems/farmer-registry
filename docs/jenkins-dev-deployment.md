# Jenkins deployment to new dev

The root `Jenkinsfile` restores delivery for the upstream Farmer layout. A merged
`develop` build validates the extension, builds six images, publishes them to ECR
using the first 12 commit characters, then upgrades the existing `farmer-registry`
Helm release in namespace `farmer`. PR and other branch builds validate and build
only. This pipeline does not deploy staging or install a new environment.

## Jenkins setup

Configure the repository as a Jenkins Multibranch Pipeline with script path
`Jenkinsfile` and branch discovery including `develop`. Retain the Git webhook;
run **Scan Multibranch Pipeline Now** after merging if the missing Jenkinsfile
previously disabled branch discovery. A merge alone cannot deploy until this
Jenkins job and its credentials are configured.

Required Jenkins plugins include Pipeline, Git/branch-source, Credentials Binding,
AWS Credentials and Timestamper. The build agent needs Git, Bash, Docker and AWS
CLI. The deployment agent labelled `vpn-agent2` needs Git, Bash, Docker, Helm 3
and kubectl, plus connectivity to the new-dev Kubernetes API, Docker Hub, package
indexes and the OpenG2P Helm repository. Both agents must allow Jenkins to run
Docker with local bind mounts. Host Python, pip and venv packages are not required.

Both stages build the Python 3.12 helper image from `ci/jenkins/Dockerfile`.
Validation runs with the repository mounted read-only as the Jenkins user's UID.
Deployment runs only the values/manifest guard in that container, without network
access or a kubeconfig mount; Helm and kubectl retain the host's VPN connectivity.

| Credential | Type and purpose |
| --- | --- |
| `aws-ecr-creds` | AWS credential binding; publish to the intended ECR account |
| `farmer-dev-kubeconfig` | Secret file; access the existing new-dev release |

Pre-create the six ECR repositories under
`openg2p/farmer-registry/{staff-api,partner-api,celery,db-seed,sanity-tests,staff-ui}`
in `ap-south-1`, and grant push access. The account is resolved from AWS STS;
the existing dev account is `379220350808`. Existing Kubernetes image-pull
credentials must allow those repositories. Never put credentials in Git.

## Upgrade behavior and ownership

- Runtime images and the inherited Registry chart stay pinned to **1.2.2-rc.544**.
  There is no root Dockerfile; Jenkins builds the six component Dockerfiles.
- The pipeline reads existing release values and checks the hostname is
  `registry.farmer-dev.oanstaging.com`. It carries forward environment values,
  Secret references, ingress routes, storage, and the worker's AWE settings.
- The optional dashboard API template preserves its resources within the Registry
  release and retains its existing independently published image.
- `farmer-connector` is a separate Helm release in `farmer`, not part of Commons.
  This pipeline neither builds nor upgrades it. Commons Base and Services remain
  independently managed.
- The schema gate checks all 36 coordinate columns and document-history
  `event_type` before and after deployment. Schema repair is an explicit operator
  action with a backup; Jenkins does not run the repair scripts.
- The seed hook applies extension metadata with geography, sample records, images
  and intake fixtures disabled. The sanity hook is required to pass; mutating E2E
  fixtures are disabled. New analytics publishing/import jobs default to disabled.
- The COSS seed entrypoint commits Registry metadata in one transaction and AWE
  metadata in a separate transaction, then runs enabled upstream widget/template
  loaders. SQL errors exit nonzero and roll back that database's metadata batch.
  Earlier database commits and object uploads are not part of a distributed
  transaction; rerun after correcting a failure. Baseline duplicate inserts retain
  existing rows, while explicit extension upserts apply reviewed COSS changes.
  Shared lookup SQL is not loaded into Registry or MDS by this job; shared catalogs
  must already be managed by the Commons migration workflow.
- Candidate validation rejects resource removal, changed existing environment or
  Secret references, changed routing/storage, and incorrect commit images.
  A rejected change requires an explicit reviewed migration, not bypassing the guard.

Helm accepts an existing release in `deployed` or `failed` state. Pending,
uninstalling, unknown and missing states block deployment. The log shows the
revision and state without exposing the Helm description. The revision/state are
checked again immediately before upgrade; a changed release requires a fresh run.

Normal upgrades from `deployed` use `--atomic --wait --wait-for-jobs`. Recovery
from `failed` retains all schema, preservation and sanity checks, but omits
`--atomic`: Helm could otherwise restore an older successful revision whose
resources/configuration differ from the failed revision being recovered. A failed
recovery stays failed for operator diagnosis; Jenkins does not edit Helm Secrets,
delete the release or automatically roll back. Success requires Helm to report
`deployed`, followed by rollout, manifest and schema checks.

Atomic rollback covers a failed normal Helm upgrade, **not database changes**
performed by seed hooks. Post-upgrade checks can also fail after Helm succeeds;
investigate before retrying. Keep the operator's database backup/recovery process.
Private values and rendered manifests are temporary, are not archived, and are
removed on exit. Inspect restricted pod logs when a hook fails. Never apply an
offline rendered manifest: chart Secret lookups require the live cluster.

On upgrade failure, Jenkins prints a classified Helm error summary plus release
history and Job/Pod status. It does not echo arbitrary Helm output, which may
contain Secrets. Unclassified errors are identified explicitly. Diagnostic
command failures do not suppress the remaining checks. The successful path joins
`helm get manifest` with `helm get hooks` before checking required workloads.
See the [seed and deployment rehearsal report](jenkins-seed-validation-20261015.md).

## Validation and first rollout

Deployment guard regression tests and Helm lint/render are part of GitHub checks.
The candidate was also rendered against values read from new dev and passed the
resource/environment preservation comparison. This is not evidence of a Jenkins
run or a deployed upgrade. After merge, verify the Jenkins build reaches publish
and deploy, the Helm revision is deployed, and UI login/intake save work.

PM issuer configuration, partner onboarding and ODK form publication are separate
rollout steps; a successful Registry deployment does not establish ODK end-to-end
approval. See [ODK geography rollout](odk-geography-rollout.md).
