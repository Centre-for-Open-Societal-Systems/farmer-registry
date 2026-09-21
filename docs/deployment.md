# Farmer Registry — deployment setup, end to end

Everything needed to build, deploy, upgrade, verify, roll back and debug the
Farmer Registry on the `far` namespace of the dev and staging clusters. Written
against the repo as of 2026-09-17 (`develop` @ PR #31 merged, PR #33 open).
Where something is *not* in the repo and only exists on a cluster or in Jenkins,
it is called out explicitly, because those are the parts that bite on a rebuild.

Rule that governs all of this: **every change to `far` — the registry release
and the shared `commons-services` release alike — goes through a pull request
and a Jenkins job.** Read-only `kubectl get/logs/exec` for diagnosis is fine.
Hand-run `helm`/`kubectl apply` on the box is not, even for a "quick fix": it is
invisible to the next build and drifts (that is how `commons-services` ended up
on a floating master-data tag nobody could reproduce).

---

## 1. Topology

### 1.1 What gets deployed

The Farmer Registry is the OpenG2P **registry platform** (`openg2p-registry`
Helm chart + base images from GitLab) plus a thin farmer layer on top:

| Piece | Comes from | Deployed as |
| --- | --- | --- |
| staff-portal-api, partner-api, celery worker, celery beat, db-seed, bene-api, id-generator, redis | `openg2p-registry` subchart (`Chart.yaml` dependency, alias `registry`) | Helm release **`farmer-registry`** |
| staff-portal-ui (1.2.1 base + farmer bundle patches) | root `Dockerfile`, target `staff-ui` | same release |
| farmer domain package (`farmer-extension/`), seed metadata, AWE policy, DCI templates | this repo, baked into the images | same release |
| sanity e2e suite | `docker/sanity-tests/Dockerfile` | same release, post-upgrade hook Job |
| analytics layer (reporting views, Superset dashboards, Insights maps content) | `helm/openg2p-farmer-registry/templates/` | same release, **disabled by CI** |
| IAM, Keycloak, AWE, Master Data, Partner Mgmt, Consent Mgr, audit manager, keymanager, (Superset off) | `openg2p-commons-services` chart | Helm release **`commons-services`** |
| PostgreSQL (`commons-postgresql-0`), Redis (`commons-redis`), MinIO (`commons-minio`) | `openg2p-commons` base chart | Helm release **`commons`** |

All three releases live in the **same namespace `far`**. The registry release
reaches the platform by in-cluster Service names that the subchart defaults
already point at (`commons-postgresql`, `commons-services-iam-staff-portal-api`,
`commons-services-master-data-api`, `commons-services-pm-partner-api`, ...).

### 1.2 Environments

| Env | Cluster | API server | Jenkins kubeconfig credential | Triggered by |
| --- | --- | --- | --- | --- |
| dev | rke2, "gen2 dev" | `https://10.0.1.166:6443` | `gen2-dev-kubeconfig` | push to `develop` |
| staging | EC2 `farmer-registry-development.oanstaging.com` | `10.0.1.212` | `staging-farmer-kubeconfig` | push to `staging` |

Both use namespace `far`, release name `farmer-registry`, and the same
`commons`/`commons-services` layout. Both are reached from the Jenkins node
labelled **`vpn-agent2`** (the only node with VPN access to the cluster API).

Hostnames are **not in git** — they live in each release's live Helm values
(see §6). Known ones on staging, for orientation:

| Purpose | Host |
| --- | --- |
| Public staff portal | `farmer-registry-development.oanstaging.com` |
| Internal staff ingress (what AWE was posting to) | `staff-farmer-registry.far.openg2p.test` |
| AWE | `awe.far.openg2p.test` |
| Keycloak (internal) | `keycloak.commons.openg2p.test` |
| Keycloak (public) | `keycloak-development.oanstaging.com` |

`*.openg2p.test` hosts are served by the cluster ingress with certificates from
a private CA (`CN = OpenG2P Local CA`, valid 2026-08-10 → 2036-08-07). Anything
inside the cluster that calls one of them over https must trust that CA — see
§4.4.

`values-dev.yaml` at the repo root names `farmer-registry.dev.openg2p.org` and an
ECR path under account `379220350808`/`oan/farmer-registry`. **Nothing reads that
file** (neither Jenkinsfile references it) and its ECR path does not match the
pipeline's; treat it as stale.

### 1.3 Git

| Remote | Repo | Role |
| --- | --- | --- |
| `origin` | `Centre-for-Open-Societal-Systems/farmer-registry` | PR target; `develop` is what dev deploys, `staging` is what staging deploys |

Fork PRs show CI as `action_required` until a COSS maintainer approves the
workflow run; that is not a failure.

---

## 2. Build: images

### 2.1 One Dockerfile, one target per service

CI builds the **root `Dockerfile`** (the same one `docker compose` builds), not
the older `docker/<service>/Dockerfile` copies — those drifted (staff-ui still on
1.1.1, APIs missing `docker/patches/patch_platform.py`) and are dead except
`docker/sanity-tests/Dockerfile`, which has no root target.

| Image | Dockerfile / target | Base | Build arg |
| --- | --- | --- | --- |
| `staff-api` | `Dockerfile` `--target staff-api` | `registry.gitlab.com/openg2p/registry/registry-platform/staff-api:${RP_VERSION}` | `RP_VERSION` |
| `partner-api` | `--target partner-api` | `.../registry-platform/partner-api:${RP_VERSION}` | `RP_VERSION` |
| `celery` (worker **and** beat) | `--target celery` | `.../registry-platform/celery:${RP_VERSION}` | `RP_VERSION` |
| `db-seed` | `--target db-seed` | `.../registry-platform/db-seed:${RP_VERSION}` | `RP_VERSION` |
| `staff-ui` | `--target staff-ui` | `openg2p/openg2p-registry-staff-ui:${STAFF_UI_VERSION}` (Docker Hub, **1.2.1**) | `DASHBOARD_URL=` (empty: no Dashboard button) |
| `sanity-tests` | `docker/sanity-tests/Dockerfile` | platform sanity image | `RP_VERSION` |
| `dashboard-ui` | `docker/dashboard-ui/Dockerfile` | — | **skipped in CI**: needs the untracked `dashboard-ui/lib/`; the chart does not deploy it |

`RP_VERSION` is **`0.0.0-develop.384`** and is pinned in three places that must
agree: `Dockerfile` (`ARG RP_VERSION`), `Jenkinsfile` (`RP_VERSION` env), and
`helm/openg2p-farmer-registry/Chart.yaml` (dependency `openg2p-registry`
version). `test/test_rp_pin_lockstep.py` fails CI if the Dockerfile and chart
disagree. Move them together with `./scripts/bump-rp-version.sh [-n] [version]`
— it checks the version exists in **both** the GitLab Helm index and the
container registry before writing anything, because the platform publishes
images before the chart index regenerates.

The API/celery/db-seed targets `pip install` `farmer-extension/` and run
`docker/patches/patch_platform.py` against the platform package. The staff-ui
target applies CSS/JS patches to the minified 1.2.1 bundle (tab overflow, farm
background, intake photo widget, detail-field wrapping), re-hashes the patched
assets (`docker/staff-ui/rehash-patched-assets.sh`, because Next serves
`/_next/static` immutable) and **fails the build if any patch no longer
matches** — so a staff-ui base bump that breaks a sed shows up at build time,
not in the browser.

### 2.2 Registry and tags

- Registry: ECR, `${AWS_ACCOUNT_ID}.dkr.ecr.ap-south-1.amazonaws.com`
- Path: `openg2p/farmer-registry/<image>`
- Tags per build: `<first 12 chars of GIT_COMMIT>` **and** `develop` (floating;
  overwritten on every build of any branch that reaches this stage)
- Login: Jenkins credential `aws-ecr-creds` (AWS credentials binding),
  `aws ecr get-login-password | docker login`

The chart's default image repositories point at
`registry.gitlab.com/openg2p/registry/farmer-registry/*:0.0.0-develop`. Those
are placeholders; CI always overrides repository **and** tag (§3.2).

`docker/build-and-push.sh [namespace] [version]` is a manual Docker Hub push of
the same targets (default namespace `rediet03`). Not used by CI.

---

## 3. Deploy: the registry pipeline (`Jenkinsfile`)

Multibranch pipeline. Every branch builds and pushes; only `develop` and
`staging` deploy.

### 3.1 Stages

| Stage | Agent | What it does |
| --- | --- | --- |
| Checkout | any | `checkout scm` |
| ECR Login | any | `aws-ecr-creds` → `docker login` |
| Build & Push | any | builds the 6 images above, pushes `<sha12>` and `develop` tags |
| Stash chart | any | stashes `helm/openg2p-farmer-registry/**` only |
| Deploy (far namespace) | **`vpn-agent2`** | `when { branch develop \|\| staging }`, `beforeAgent true` so other branches never queue for the VPN node |
| post/always | — | `docker image prune -f`, `docker logout` |

### 3.2 The deploy stage, step by step

1. `unstash` the chart; `helm repo add openg2p-gitlab
   https://gitlab.com/api/v4/projects/84460547/packages/helm/stable`;
   `helm dependency build` (pulls `openg2p-registry` at the pinned version).
2. Writes `/tmp/values-far-cicd-<build>.yaml` — the **only** values CI owns:
   - `registry.{staffApi,staffUi,partnerApi,celeryWorker,celeryBeat,dbSeed,sanity}.image.{repository,tag}` → ECR + `<sha12>`
   - `registry.dbSeed.loadAttributes: false`
   - `analytics.{bulkSample,reportingViews,dashboards}.enabled: false`, `mapsContent.enabled: false` — registry only, no analytics layer on these clusters
3. `helm get values farmer-registry -n far -o yaml` → `/tmp/far-values-current-<build>.yaml`.
   **This is what preserves the environment**: hostnames, Keycloak/IAM wiring,
   cookie domain, CA-bundle mount all live in the release's values, not in git.
   Only "release: not found" is tolerated (first install, proceeds with chart
   defaults, which render placeholder `*.openg2p.org` hosts); any other read
   error aborts the build rather than reset the environment.
4. `helm template` with live values + CI values → `/tmp/far-new-<build>.yaml`
   (rendered manifest, in the build log by line count; useful for `grep`).
5. Starts a background loop copying logs of `farmer-registry-(db-seed|iam-register|sanity)-*`
   pods every 5 s — hook Jobs delete their pods on failure and Helm only
   reports `BackoffLimitExceeded`.
6. `helm upgrade --install farmer-registry helm/openg2p-farmer-registry -n far
   -f <live> -f <ci> --timeout 20m`. On failure prints the captured hook logs
   and exits 1.
7. `kubectl rollout status` (180 s each) for `staff-portal-api`,
   `staff-portal-ui`, `partner-api`, `celery-worker`, `celery-beat-producer`.
8. Prints `succeeded/failed` counts of the `farmer-registry-db-seed` and
   `farmer-registry-sanity` Jobs.

Values precedence (later wins): chart defaults (subchart) → wrapper chart
`values.yaml` → live release values → CI values. So a key set in the wrapper
chart is **overridden by the live values if they also carry it**. If you change
a key in `helm/openg2p-farmer-registry/values.yaml` and it does not take effect,
check `helm get values` for a live override.

### 3.3 Hooks that run on every deploy

From the subchart, `post-install,post-upgrade`, `hook-delete-policy:
before-hook-creation` (the previous Job is deleted right before the new one is
created, so the last run's Job stays visible until the next deploy):

| Weight | Job | Notes |
| --- | --- | --- |
| pre-install/upgrade | `awe-callback-hmac-secret` | generates `farmer-registry-awe-callback-hmac` (key `hmac-secret`) if absent |
| 10 | `farmer-registry-db-seed` | registry schema/meta_data, AWE policy + `callback_secret` (and, from PR #33, repoints open AWE requests), sample data/images/templates per `registry.dbSeed.load*` |
| 11 / 12 / 13 | sanity `pm-seed`, `cm-seed`, `data-seed` | seed a persistent sanity partner into PM/CM and a sanity farmer |
| 19 / 20 | `iam-register` configmap + Job | registers the "Farmer Registry" tile, roles and permissions in IAM |
| 25 | `farmer-registry-sanity` | farmer e2e suite (`registry.sanity.*`), `runE2e`/`failOnError` at subchart defaults |
| 15 / 20 / 30 | analytics jobs | **disabled** by the CI overlay |

Consequences: a deploy is never a no-op — db-seed, sanity seeds and
iam-register all re-run. The seed SQL is written to be idempotent for that
reason; a new seed file must be too.

Not hooks, but Jobs that ship **inside the registry release** (subchart
dependencies, created at install; a Job spec is immutable, so a changed spec
on upgrade fails until the old Job is deleted):

| Job | Subchart | Does |
| --- | --- | --- |
| `farmer-registry-postgres-init` | `postgres-init` 1.2.0 | creates DB `farmer_registry`, role `farmer_registry_user` (+ `pg_trgm`) on `commons-postgresql` using the `commons-postgresql` Secret's `postgres-password`; writes Secret `farmer-registry` / key `farmer-registry-db-user` |
| `farmer-registry-idgen-pg-init` | id-generator's own `postgres-init` | same for `farmer_registry_idgenerator` / Secret `farmer-registry-idgenerator` |
| `farmer-registry-keycloak-init` | `keycloak-init` 1.1.1 | against `http://commons-keycloak:80` (admin password from Secret `commons-keycloak` / `admin-password`): creates client `farmer-registry-staff-portal` in realm `staff` with redirect `https://<registryHostname>/*`, the 11 client roles, users `admin` (Operations + Technical Administrator) and the AWE demo approvers (`alex.carter` etc., password `global.aweApproverUserPassword`); writes Secret `farmer-registry-staff-portal` / `client_secret` |
| `farmer-registry-redis-master` | bitnami `redis` 19.6.4 | the registry's own Redis (not a Job — a StatefulSet) |

### 3.4 What the registry release expects to already exist in `far`

Objects the subchart references by default name and does **not** create itself
(override in live values if an environment names them differently):

| Object | Kind | Key(s) | Created by |
| --- | --- | --- | --- |
| `commons-postgresql` | Secret | `postgres-password` | `commons` — the registry's `postgres-init` uses it to create its own DB/role |
| `commons-keycloak` | Secret | `admin-password` | `commons` / Keycloak — the registry's `keycloak-init` uses it to create its own client |
| `commons-minio` | Secret | `root-user`, `root-password`, `readonly-user`, `readonly-password` | `commons` |
| `master-data` | Secret | `master-data-db-user` | commons-services |
| `awe-db-user` | Secret | `awe-db-user-password` | commons-services (db-seed writes the AWE policy + callback secret into DB `awe`) |
| `commons-redis` | Service | — | `commons` (auth session store) |
| `commons-keycloak`, `commons-services-{iam-staff-portal-api,master-data-api,pm-partner-api,pm-staff-portal-api,cm-partner-api,cm-api,auditmanager,keymanager}` | Service | — | `commons` / commons-services |
| `far-ca-bundle` | ConfigMap | `ca-bundle.pem` | **hand-applied 2026-08-16, not Helm, not git** — §4.4 |

Objects the registry release creates for itself (so they must **not** be
pre-created, or the Jobs conflict): Secret `farmer-registry`
(`farmer-registry-db-user`), Secret `farmer-registry-idgenerator`, Secret
`farmer-registry-staff-portal` (`client_secret`), Secret
`farmer-registry-awe-callback-hmac` (`hmac-secret`), DBs `farmer_registry` and
`farmer_registry_idgenerator`, Keycloak client `farmer-registry-staff-portal`,
its own Redis `farmer-registry-redis-master`.

DB names/users derive from the release name: `farmer_registry` /
`farmer_registry_user` on `commons-postgresql:5432`; AWE DB `awe` /
`awe_user`; master data `master_data` / `master_data_user`. All three live in
the one `commons-postgresql-0` instance, which is why `helm uninstall` leaves
the databases behind (see §11).

**Upload size on the host reverse proxy.** Browsers reach the portal through
an nginx on the EC2 host (`nginx/1.24.0 (Ubuntu)` in its error pages), which
proxies to the cluster's Istio ingress gateway (Envoy, no request-body limit
of its own). nginx's default `client_max_body_size` is 1 MB and the intake
form uploads files of up to 10 MB (`maxSize` on the file widgets: land
certificate, farmer photo): anything larger was answered by the host with
`413 Request Entity Too Large` and never reached the API. The portal says so
("The file is too large for the server to accept") and refuses to save the
section; images are resized in the browser to about 1 MB before upload, PDFs
are sent as picked.

Applied 2026-09-21 in `/etc/nginx/sites-available/openg2p-public-farmer-dev.conf`
(the `server_name farmer-registry-development.oanstaging.com` block, right
after `server_name`; backup `*.conf.bak-20260921` beside it):

```nginx
client_max_body_size 12m;
```

then `nginx -t && systemctl reload nginx`. Verified with a 3 MB multipart
POST to `/api/shared/upload-document`: 413 before, 401 (login required --
the body reached the API) after; 13 MB still 413. Only this site carries the
line: there is no `http {}`-level value, so the other
`*-development.oanstaging.com` portals on the host (crop, livestock, ...)
are still on the 1 MB default and need the same line if they upload files.

---

## 4. Deploy: the shared platform (`ci/commons-services/`)

The `commons-services` release was originally installed by hand. This directory
puts the parts the registry depends on under version control and gives them a
**standalone, manual-only** Jenkins job — deliberately not a stage of the
registry pipeline, because the chart's post-upgrade hooks (geo seed,
iam-register) re-run on every `helm upgrade` and the platform changes on its own
cadence. Suresh explicitly does not want platform upgrades inside the per-build
pipeline.

### 4.1 Files

| File | Purpose |
| --- | --- |
| `upgrade.sh` | the upgrade end to end; pins `CHART_VERSION=2.3.0-rc.217` |
| `Jenkinsfile` | Pipeline job: `ENVIRONMENT` (`dev`/`staging`), optional `CHART_VERSION`, `CONFIRM` boolean; no triggers; `disableConcurrentBuilds` |
| `values-far.yaml` | overlay applied on top of the live values: master-data image path moved to `platform-services/`, geo-seed image path, `objectStore.endpoint: ""`, `masterDataUi/superset/inji-certify` disabled |
| `master-data-schema-topup.sql` | idempotent `ADD COLUMN IF NOT EXISTS` set for master-data, run in the pod before the upgrade |
| `apply-sql-in-pod.py` | runs SQL from stdin inside the master-data-api pod with its own DB env (old or new prefix) |
| `README.md` | rationale, how to regenerate the top-up SQL, why rc.217 |

### 4.2 Job setup (one-time, in Jenkins)

Pipeline job → "Pipeline script from SCM" → script path
`ci/commons-services/Jenkinsfile`, branch `develop`, agent label `vpn-agent2`.
Run with *Build with Parameters*; with `CONFIRM` unticked it checks out and
stops. The pre-upgrade live values are archived with the build as
`commons-services-values-rev<N>.yaml`.

Check the job exists before relying on it — PR #30 only merged on 2026-09-16.

### 4.3 What `upgrade.sh` does

1. `helm get values commons-services -n far` → saved as
   `./commons-services-values-rev<N>.yaml`; prints the exact `helm rollback`
   command. A missing release aborts: first install is not this script's job.
2. `kubectl exec deploy/commons-services-master-data-api -- python -c
   apply-sql-in-pod.py < master-data-schema-topup.sql`.
3. `helm template` with live values + `values-far.yaml`; prints the unique
   `image:` lines (this is where you catch a floating/unpullable tag).
4. `helm upgrade commons-services openg2p-gitlab/openg2p-commons-services
   --version 2.3.0-rc.217 -f <live> -f values-far.yaml --timeout 20m`, with
   the same hook-log capture as the registry pipeline (`*-(seed|register|init)-*`).
5. `kubectl rollout status deploy/commons-services-master-data-api`, then from
   the **staff-ui pod** fetches `$MASTERDATA_BACKEND_API_URL/openapi.json` and
   fails unless `/geo/get_all_geo_levels` is served (the G2R-172 regression).

Subcharts at rc.217: master-data `1.1.0-rc.55`, IAM `1.4.0-rc.90`,
audit-manager `1.0.1`, `openg2p-awe 0.0.0-develop.70` (no alias, so its values
key is `openg2p-awe:`). `0.0.0-develop.N` tags of OpenG2P images are **rebuilt
in place** — a local pull of the same tag proves nothing about what a pod runs;
read the truth from the pod (`openapi.json`, `imageID`, `env`).

### 4.4 TLS trust inside the cluster (the CA bundle)

`far-ca-bundle` (ConfigMap, key `ca-bundle.pem`, 122 certs = 121 public roots +
the local CA) is mounted into `farmer-registry-staff-portal-api` at
`/etc/ssl/local-ca/` with `SSL_CERT_FILE=/etc/ssl/local-ca/ca-bundle.pem`. That
wiring is in the **live values**, not the chart. The ConfigMap itself has no
Helm labels/annotations, is in no release manifest, and was created by hand
on 2026-08-16. AWE has no bundle at all.

This is an open ownership question with Suresh (G2R-96 comment 24918). Until it
is settled: a fresh namespace or rebuild must recreate this ConfigMap by hand
**before** the first registry deploy, or `staff-portal-api` fails TLS to every
`*.openg2p.test` host. `SSL_CERT_FILE` *replaces* Python's default trust store,
so the bundle must keep the public roots (it does).

PR #33 removes the registry's own dependence on this for the AWE callback by
calling `staff-portal-api` in-cluster over http.

---

## 5. Cluster access for CI (`ci/k8s/farmer-deploy-rbac.yaml`)

Applied **once, by the cluster admin**, per cluster:

```sh
sudo KUBECONFIG=/etc/rancher/rke2/rke2.yaml kubectl apply -f ci/k8s/farmer-deploy-rbac.yaml
```

Creates in `far`: ServiceAccount `farmer-ci`, long-lived token Secret
`farmer-ci-token`, RoleBinding to the built-in ClusterRole `admin` (namespace
scoped), plus Role `ci-deploy-istio` (`networking.istio.io`,
`security.istio.io`, all verbs) because the chart creates VirtualServices and
`admin` does not cover them.

Then build the kubeconfig on the box (the exact commands are in the manifest's
header comment: extract `ca.crt` and `token` from `farmer-ci-token`,
`kubectl config set-cluster/set-credentials/set-context`, verify with
`kubectl auth can-i list secrets -n far`) and upload it to Jenkins as a
**Secret file** credential with ID `gen2-dev-kubeconfig` (dev) or
`staging-farmer-kubeconfig` (staging). PR #27 switched the dev credential id to
`gen2-dev-kubeconfig`; check `origin/develop` before copying ids.

---

## 6. Live values — what is on the cluster but not in git

Both releases carry environment-specific values that no file in this repo
holds. Read them with:

```sh
helm get values farmer-registry -n far -o yaml
helm get values commons-services -n far -o yaml
helm get values commons -n far -o yaml
```

For `farmer-registry` expect at least: `global.registryHostname`,
`global.keycloakBaseUrl`, cookie domain / IAM URLs, `global.minioHost` +
`minioSecure` (must be a browser-resolvable host — pre-signed URLs are signed
against it and the staff-ui CSP is derived from it), the `far-ca-bundle` volume
+ mount + `SSL_CERT_FILE` on staff-portal-api, and possibly `publicStaffUi.*`.

**Changing a live value is currently a hand-run `helm upgrade -f`**, which
contradicts the PR-only rule. There is no tracked per-environment values file
yet. Until there is, the least-bad path: put the change in
`helm/openg2p-farmer-registry/values.yaml` if it is environment-independent
(as PR #33 does), or raise it with Suresh if it is not. **Back up
`helm get values` before any manual change.**

---

## 7. First install of a new environment (checklist)

Ordered. Items marked *(manual)* are not scripted anywhere in this repo.

1. *(manual)* Cluster with Istio; namespace `far`; DNS for the public and
   `*.openg2p.test` hosts; ingress TLS from the local CA.
2. *(manual)* Install `openg2p-commons` as release `commons` (PostgreSQL
   with the `commons-postgresql` Secret, Redis, MinIO, Keycloak with the
   `commons-keycloak` Secret). The registry creates its own database and
   Keycloak client from these at install (§3.3) — do not pre-create them.
3. *(manual)* Install `openg2p-commons-services` as release `commons-services`
   with the **full** environment values (hostnames, Keycloak realm `staff`,
   IAM, AWE, master-data with `geoSeed.countryPack: ETH`, PM, CM, audit
   manager). `ci/commons-services/upgrade.sh` refuses to first-install.
4. *(manual)* Create `far-ca-bundle` (§4.4). Optionally `openg2p-ca-cert`
   (cluster-wide, `ca.crt`, used by UI deployments via `NODE_EXTRA_CA_CERTS`).
5. Apply `ci/k8s/farmer-deploy-rbac.yaml`; build the kubeconfig; add the
   Jenkins Secret-file credential (§5).
6. Jenkins: multibranch pipeline on the repo; credentials `aws-ecr-creds`,
   env `AWS_ACCOUNT_ID`; node `vpn-agent2` with `helm`, `kubectl`, VPN.
   Standalone `ci/commons-services` job (§4.2).
7. First registry deploy: push to `develop` (dev) / `staging`. With no release
   present the stage installs with chart defaults → placeholder
   `*.openg2p.org` hosts.
8. *(manual, once)* `helm upgrade farmer-registry ... -f <env values>` to set
   the real hostnames/Keycloak/IAM/CA-bundle values. Every later pipeline run
   preserves them. (Back them up; they are the only copy.)
9. Verify (§8). Then log in as `admin` and confirm the "Farmer Registry" tile
   exists in IAM.

---

## 8. Post-deploy verification

```sh
NS=far; R=farmer-registry

# Release state and revision
helm list -n $NS                                     # both releases 'deployed'
helm history $R -n $NS | tail -3

# Workloads
kubectl -n $NS get deploy,job -l app.kubernetes.io/instance=$R
kubectl -n $NS get pods | grep -v Running | grep -v Completed   # should be empty

# Images actually running match the build
kubectl -n $NS get deploy $R-staff-portal-api -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

# Hook outcomes
kubectl -n $NS get job $R-db-seed $R-sanity -o wide
kubectl -n $NS logs job/$R-db-seed --tail=50

# Master data routes as the UI sees them
kubectl -n $NS exec deploy/$R-staff-portal-ui -- sh -c 'wget -qO- "$MASTERDATA_BACKEND_API_URL/openapi.json"' | grep -o '"/geo/[a-z_]*"' | sort -u

# AWE wiring (after PR #33)
kubectl -n $NS exec -i commons-postgresql-0 -- sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U postgres -d awe -X -c "SELECT id, caller_service FROM callback_secret;"'
kubectl -n $NS exec -i commons-postgresql-0 -- sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U postgres -d awe -X -c "SELECT status, count(*) FROM webhook_delivery GROUP BY 1;"'

# Celery is picking up approved submissions
kubectl -n $NS logs deploy/$R-celery-beat-producer --tail=20 | grep intake_form_register_ingest
```

Then in the browser: log in, open an intake submission, approve it in AWE, and
confirm `approval_status = APPROVED` and `register_ingest_process_status`
reaches `PROCESSED` within ~1 minute (beat polls every 20 s).

---

## 9. Rollback

**Registry release**

```sh
helm history farmer-registry -n far
helm rollback farmer-registry <revision> -n far
```

Rolling back re-runs the hooks of the *older* chart with the older images.
Seed SQL is idempotent, so that is safe; data written by a newer seed is not
undone. To redeploy a specific commit instead, re-run the Jenkins build of that
commit (images are tagged by sha, so nothing needs rebuilding if they still
exist in ECR).

**commons-services**

`upgrade.sh` prints `helm rollback commons-services <N> -n far` at the start
and archives the pre-upgrade values with the Jenkins build. The master-data
schema top-up is additive and needs no undo.

---

## 10. Troubleshooting

| Symptom | Cause / where to look |
| --- | --- |
| `helm list` shows a release `failed` | last upgrade's hook Job failed or timed out. `helm history`, then the hook logs printed in the Jenkins build. `helm upgrade` still runs on a `failed` release (only `pending-*` blocks it), but understand the failure first. `farmer-registry` was `failed` at rev 15 (2026-09-15) when last checked. |
| `ImagePullBackOff` on `commons-services-*` | image path moved to `registry.gitlab.com/openg2p/platform-services/...`; the old `openg2p/master-data-service/...` path denies anonymous pulls. `values-far.yaml` overrides master-data and geo-seed; PR #32 adds partner-management. `cm-api-expire-*` and `kc-sa-role-*` were in this state on 2026-09-17. |
| Location dropdowns 404 (`get_all_g2p_geo_levels`) | master-data serving old route names — the reason `ci/commons-services` exists. Verify on the pod, not on a local image of the same tag. |
| Approval stuck in `PENDING`, AWE shows `approved` | webhook not delivered. `SELECT status, left(last_error,80), count(*) FROM webhook_delivery GROUP BY 1,2` in the `awe` DB. Before PR #33: `CERTIFICATE_VERIFY_FAILED` to the ingress host. |
| Submission `APPROVED` but no farmer created | `register_ingest_process_status` — if `NOT_APPLICABLE` the approval was set by hand without the ingest flag; if `FAILED` read `register_ingest_process_last_error_code` and the celery-worker log. |
| Farmer photo missing, no error | `global.minioHost` points at an in-cluster name; must be browser-resolvable and identical to the signer's host (`test/staff-ui/test_minio_presigned_host.py`). |
| Staff-ui build fails `PATCH NOT APPLIED` | a bundle sed no longer matches the base 1.2.x build; re-anchor the patch in the root `Dockerfile`. |
| Hook Job log gone, Helm says `BackoffLimitExceeded` | expected; use the copies the pipeline prints. Between builds: `kubectl get jobs -n far`, the last Job survives until the next deploy. |
| `sh: set: pipefail: invalid option` in a container script | file checked out with CRLF from Windows. Repo clones must use `core.autocrlf=false`; no `.gitattributes` exists. |
| Deploy stage never starts on a feature branch | correct: only `develop`/`staging` deploy. |
| Live hostnames reset to `*.openg2p.org` | `helm get values` failed or the release was reinstalled without `-f <live>`. Restore from the last saved values. |

---

## 11. Uninstall

`scripts/uninstall-registry.sh` removes a registry release and everything it
touched that `helm uninstall` leaves behind: this registry's Superset assets,
leftover hook Jobs/pods, labelled Secrets/ConfigMaps, the Postgres DB and role
inside `commons-postgresql-0`, its IAM rows (`staff_portal_applications`,
roles/permissions for `farmer-registry-staff-portal`), PVCs and released PVs.
It deliberately leaves the shared sanity partner in PM and its CM binding.
Read its header before running; it is destructive and, per the PR-only rule,
should be a deliberate act agreed with Suresh, not a debugging step.

---

## 12. Local development (not the deployment path)

`docker compose -p <project> --env-file local/.env up -d --build` runs the same
images against a local Postgres/Redis/MinIO/Keycloak/IAM/master-data. Always
pass `-p`: `docker-compose.yml` names the project `farmer-registry` and a bare
`up` on a machine with an older project attaches to the wrong volumes. See
`local/README.md`. Local uses the in-cluster-style AWE callback
`http://farmer-registry-staff-api:8000/awe/webhooks/decision`, which is what
PR #33 aligns the cluster with.

---

## 13. Known gaps (as of 2026-09-17)

1. **No tracked per-environment values** for either release; hostnames and the
   CA-bundle wiring exist only as live Helm values. A rebuild depends on a
   `helm get values` backup someone remembered to take.
2. **`far-ca-bundle` is hand-applied** (§4.4). Decision pending with Suresh.
3. **Analytics layer is disabled** by the CI overlay; `dashboard-ui` is not
   built (untracked `lib/`) and not deployed. The staff-ui is built with an
   empty `DASHBOARD_URL`.
4. **`values-dev.yaml` is stale** (different ECR account/path, unreferenced).
5. **`farmer-registry` release was `failed` at rev 15**; cause not yet
   established.
6. **AWE webhook client has no `verify_ssl`/CA setting** upstream; only
   matters again if an `https://` callback is reintroduced.
7. **11 pre-AWE submissions** on staging have no `awe_request_id` and will
   never move through approval without a backfill.
8. **Live-value changes have no PR path** (§6).
