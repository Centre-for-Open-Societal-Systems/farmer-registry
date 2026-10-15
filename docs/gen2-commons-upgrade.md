> Historical server diagnosis and rollout prerequisites from PR #91. The repository now uses the upstream RC layout; old Jenkins/local-gen2 commands below are not the new deployment procedure. See [current adoption notes](coss-upstream-adoption.md).

# Gen2 dev: registry in `farmer`, shared services in `commons`

This profile is based on COSS `develop` at `67d47a8` (including DevOps PR #92). It changes **development
only**. Staging continues to use its existing live values; no shared platform
upgrade runs as part of the farmer pipeline.

## Release contract

| Namespace | Helm release | Chart | Version |
| --- | --- | --- | --- |
| `commons` | `commons` | `openg2p-commons-base` | `2.3.3` (deployed) |
| `commons` | `commons-services` | `openg2p-commons-services` | `2.3.4-rc.245` (deployed) |
| `farmer` | `farmer-registry` | local farmer wrapper, dependency `openg2p-registry` | `1.2.2-rc.544` platform/images (upgrade target) |

Sources: [Commons Base release](https://github.com/OpenG2P/versions/blob/develop/commons/versions/2.3.3.md),
[Commons Services RC](https://github.com/OpenG2P/versions/blob/develop/commons/versions/2.3.4-rc.245.md),
[registry RC](https://github.com/OpenG2P/versions/blob/develop/registry-platform/versions/1.2.2-rc.544.md),
[deployment automation](https://github.com/OpenG2P/openg2p-deployment/tree/main/automation/environment).
The current shared version pair is authoritative: this registry change does not
upgrade Base to the services RC or substitute development/standalone builds.
Upstream Farmer Registry 1.2.0
is an architecture reference, not the registry-platform version: its published
wrapper pins platform `0.0.0-develop.296`.

The platform owner manages `environment: commons` and the shared chart versions
in the deployment repository. Their real domain is not derived from a namespace.
This farmer repo does not install/migrate Commons or move its databases/objects. The
legacy `ci/commons-services` job and `values-far.yaml` target the old `far`
topology and must NOT be used to upgrade shared Gen2 dev. In particular, the RC
uses `master-data.masterDataApi`, not `masterData.masterDataAPI`.

## Before merging/enabling the dev deployment

1. The platform owner verifies both releases and actual service names in
   `commons`, database/role names (`farmer_registry`, `master_data`, `awe`), Redis
   session instance (`commons-redis-master`, DB 0), Keycloak realm `staff`, and
   the reachable browser hostnames. **If an existing farmer database/object
   store is moving, restore/migrate its contents first**; connecting to a new
   empty Commons instance is not a data migration.
2. Verify the following namespace-local credentials in `farmer` using the
   approved secret-management process. Never commit or log their contents.
   Namespace-qualified DNS does not allow a `secretKeyRef` to read `commons`.

   | Secret in `farmer` | Required keys |
   | --- | --- |
   | `commons-postgresql` | `postgres-password` |
   | `commons-keycloak` | `admin-password` |
   | `commons-minio` | `root-user`, `root-password`, `readonly-user`, `readonly-password` |
   | `master-data-db-user` | `master-data-db-user-password` |
   | `awe-db-user` | `awe-db-user-password` |
   | `commons-services-staff-portal` | `client_secret` (Master Data/PM service-token calls) |

   If the e2e sanity suite is enabled, also provision its external credentials:
   `audit-manager/audit-manager-db-user` and
   `consent-manager/client_secret` (check the rendered chart for any additional
   references). These optional references are NOT required for smoke-only runs.
   Do not pre-create the registry DB/user, ID-generator or registry Keycloak
   client secrets: the init Jobs create them. Do not rotate an existing AWE
   callback HMAC secret; pending webhook deliveries depend on it.
3. Enable service accounts on `farmer-registry-staff-portal` for worker AWE
   client-credentials authentication. Keep IAM/Keycloak application mnemonics
   distinct for farmer/crop/live. AWE must trust the real external Keycloak
   issuer, including any approved alternative public hostname. Ensure a token
   requested internally actually carries that accepted issuer; a hostname
   setting alone does not prove it. Review NetworkPolicies permitting `farmer` to
   reach shared services and shared AWE to call back into `farmer`.
4. Preserve/provision the CA ConfigMaps and complete CA bundle referenced by
   live API/UI volumes. Internal token URLs do not remove the browser's HTTPS
   requirements or every service's CA dependency. Never disable TLS verification
   as a workaround.
5. Check `docs/registry-platform-1.2.2-upgrade.md`. Coordinate type migrations
   must be rehearsed on a restored database before any live execution. Helm
   rollback cannot undo schema changes or restore data.
   The existing-pod preflight now queries coordinate column types in an explicit
   read-only transaction and blocks rc.544 if any remain `varchar`. It does not
   import the application, invoke startup hooks or perform a migration. A first
   install with no existing pod still needs owner confirmation of DB readiness.
   The same gate checks document-history `event_type`, required by rc.544 when
   promoting intake attachments. Review the explicit operator-run migration at
   `ci/gen2/migrations/document_history_event_type.sql`; it is not a Helm hook.
6. Preserve the existing platform-owned `commons-services-awe` ExternalName in
   `farmer`, targeting `commons-services-awe.commons.svc.cluster.local`. It is
   required by the upstream seed health wait. The chart does NOT create/adopt it;
   the preflight checks its type and target only. Missing or wrong aliases fail
   before the upgrade; correct aliases do not need Helm ownership annotations.
7. DevOps PR #92 configures `farmer-dev-kubeconfig` for the new server and
   `farmer` namespace. Retain that credential and verify the deployed account
   against `ci/k8s/farmer-deploy-rbac.yaml`, checking
   the actual CA, API endpoint and VPN connectivity. No `far`/`common` namespace
   is created. Staging retains its separate legacy RBAC manifest and values.

The farmer CI account still needs access only to `farmer`. No additional read
permission on `commons` Secrets is granted. The platform owner verifies the
shared release version independently; the namespace-local preflight does not
claim to verify it.

Read-only seed findings and remaining data-repair work are recorded separately
in [gen2-db-seed-diagnosis.md](gen2-db-seed-diagnosis.md). A successful seed Job
or smoke-only sanity suite is not evidence that data relationships are correct.

The new dev connector's confirmed PM issuer/onboarding failures, repair order,
and consolidation of PRs #88/#89 into the single #91 rollout are documented in
[gen2-connector-diagnosis.md](gen2-connector-diagnosis.md). Resolve those shared
PM prerequisites as well as the registry schema gate before expecting ODK
ingestion to succeed.

## Configuration and CI precedence

`Jenkinsfile` applies the exact same arguments when rendering and upgrading:

1. Wrapper/subchart defaults.
2. Saved live farmer values (keep browser URLs, cookies, certificate mounts,
   ingress settings, registry/client identity and any public staff UI).
3. `helm/openg2p-farmer-registry/environments/dev-commons.yaml` on `develop`,
   or the empty `staging-legacy.yaml` on `staging`.
4. Optional `GEN2_BROWSER_VALUES_FILE` on the VPN agent, for approved browser
   URLs/CA references (no passwords/tokens). It can also be an approved tracked
   environment file. See `ci/gen2/browser-values.example.yaml`; replace **every**
   example hostname. This is required for a first install with no live values.
5. CI-built ECR images/dashboard settings.

The dev profile deliberately owns internal wiring and seed safety, so stale
live short-name values cannot override it. Browser endpoints are NOT guessed
from the Kubernetes namespace: their real DNS may have a different suffix.
The manifest gate rejects cluster-only/example/default browser URLs and a
cookie domain that does not cover both the IAM and farmer portal hosts. It
checks MinIO's signing hostname agrees with the UI CSP and preserves CSRF.
An enabled `publicStaffUi.env` receives the same common Master Data, public
logout, application identity and CSP overrides. Its own browser hostname, IAM
URL and cookie scope are preserved and checked by the manifest gate too.

Application calls use `*.commons.svc.cluster.local`. The existing platform-owned
ExternalName Service `commons-services-awe` in `farmer` supports rc.544's db-seed
health wait, which hardcodes that short name instead of using `aweBaseUrl`.
AWE callbacks use `http://farmer-registry-staff-portal-api.farmer.svc.cluster.local/
awe/webhooks/decision` (one URL, no newline) and retain HMAC authentication.
Metadata/templates and geo-widget synchronization remain enabled; geo/sample
records/images/bulk sample loaders are disabled. Novu notifications are off
because this Commons RC does not bundle Novu.

The deploy node needs `python3` with `venv` support, `pip`, `bash`, `helm`,
`kubectl` and access to PyPI/the Helm repository. Validation dependencies are
pinned in `ci/gen2/requirements.txt`. The preflight checks presence of Secret
keys without emitting their values and rejects a missing/wrong-target AWE
alias before any Helm upgrade. The unauthenticated dashboard API remains
ClusterIP-only: this pipeline no longer invents an ingress hostname outside the
existing gateway's `*.farmer-dev.oanstaging.com` hosts. A separate private route
requires explicit review before enabling it.

## Verification

Offline checks (no credentials or cluster required):

```sh
helm repo add openg2p https://openg2p.github.io/openg2p-helm
helm dependency update helm/openg2p-farmer-registry
mkdir -p .cache/gen2-charts
helm pull openg2p/openg2p-commons-base --version 2.3.3 --destination .cache/gen2-charts
helm pull openg2p/openg2p-commons-services --version 2.3.4-rc.245 --destination .cache/gen2-charts
python -m pip install pytest -r ci/gen2/requirements.txt
helm lint helm/openg2p-farmer-registry \
  -f helm/openg2p-farmer-registry/environments/dev-commons.yaml --strict
python -m pytest test/test_gen2_common_helm.py test/test_rp_pin_lockstep.py -q
```

GitHub Checks renders the real pinned chart and tests both good and broken
wiring. Example browser values are valid ONLY as test fixtures; the deployment
validator rejects them. Jenkins validates the final rendered live + environment
+ CI manifest, then checks namespace-local prerequisites before the upgrade.

On a disposable restored database, run the existing rc.544 intake regression
test and platform-patch/UI-upload checks. Once the platform owner approves the
live rollout, verify login/refresh/logout, geo dropdowns and permissions across
registries, intake save/read-back, photo/certificate uploads, ODK ingestion,
AWE approval/callback → processed register, partner signature/consent denial,
and dashboard queries. `/ping` or HTTP 200 alone is not success: check response
bodies, webhook delivery and ingest status. Enable full sanity e2e only with the
owner's approval because it writes fixtures into shared PM/CM/AWE services.

Archive database/object-store backups, previous Helm values/revisions and image
digests before rollout. Keep both schema-restoration and image/Helm rollback
procedures; do not uninstall/reseed the shared platform to recover.
