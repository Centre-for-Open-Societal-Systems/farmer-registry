# Gen2 dev: shared Commons in `common`

This profile is based on COSS `develop` at `c5cd54f`. It changes **development
only**. Staging continues to use its existing live values; no shared platform
upgrade runs as part of the farmer pipeline.

## Release contract

| Namespace | Helm release | Chart | Version |
| --- | --- | --- | --- |
| `common` | `commons` | `openg2p-commons-base` | `2.3.4-rc.245` |
| `common` | `commons-services` | `openg2p-commons-services` | `2.3.4-rc.245` |
| `far` | `farmer-registry` | local farmer wrapper, dependency `openg2p-registry` | `1.2.2-rc.544` platform/images |

Sources: [Commons RC](https://github.com/OpenG2P/versions/blob/develop/commons/versions/2.3.4-rc.245.md),
[registry RC](https://github.com/OpenG2P/versions/blob/develop/registry-platform/versions/1.2.2-rc.544.md),
[deployment automation](https://github.com/OpenG2P/openg2p-deployment/tree/main/automation/environment).
The two Commons charts must use the same RC. Do not take development builds or
substitute newer standalone dependency versions. Upstream Farmer Registry 1.2.0
is an architecture reference, not the registry-platform version: its published
wrapper pins platform `0.0.0-develop.296`.

The platform owner selects `environment: common`, `commons_base.chart_version:
2.3.4-rc.245` and `commons_services.chart_version: 2.3.4-rc.245` in the deployment
repository's environment configuration, with the **real** base domain. This
farmer repo does not install/migrate Commons or move its databases/objects. The
legacy `ci/commons-services` job and `values-far.yaml` target the old `far`
topology and must NOT be used to upgrade shared Gen2 dev. In particular, the RC
uses `master-data.masterDataApi`, not `masterData.masterDataAPI`.

## Before merging/enabling the dev deployment

1. The platform owner verifies both releases and actual service names in
   `common`, database/role names (`farmer_registry`, `master_data`, `awe`), Redis
   session instance (`commons-redis-master`, DB 0), Keycloak realm `staff`, and
   the reachable browser hostnames. **If an existing farmer database/object
   store is moving, restore/migrate its contents first**; connecting to a new
   empty Commons instance is not a data migration.
2. Provision the following namespace-local credentials in `far` using the
   approved secret-management process. Never commit or log their contents.
   Namespace-qualified DNS does not allow a `secretKeyRef` to read `common`.

   | Secret in `far` | Required keys |
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
   setting alone does not prove it. Review NetworkPolicies permitting `far` to
   reach shared services and shared AWE to call back into `far`.
4. Preserve/provision the CA ConfigMaps and complete CA bundle referenced by
   live API/UI volumes. Internal token URLs do not remove the browser's HTTPS
   requirements or every service's CA dependency. Never disable TLS verification
   as a workaround.
5. Check `docs/registry-platform-1.2.2-upgrade.md`. Coordinate type migrations
   must be rehearsed on a restored database before any live execution. Helm
   rollback cannot undo schema changes or restore data.
6. An old manually installed `commons-services-awe` alias in `far` blocks Helm
   ownership of the new alias. The preflight stops instead of taking it over.
   Have the platform owner resolve its ownership deliberately; do not broadly
   delete the other aliases/services.

The farmer CI account still needs access only to `far`. No additional read
permission on `common` Secrets is granted. The platform owner verifies the
shared release version independently; the namespace-local preflight does not
claim to verify it.

## Configuration and CI precedence

`Jenkinsfile` applies the exact same arguments when rendering and upgrading:

1. Wrapper/subchart defaults.
2. Saved live farmer values (keep browser URLs, cookies, certificate mounts,
   ingress settings, registry/client identity and any public staff UI).
3. `helm/openg2p-farmer-registry/environments/dev-common.yaml` on `develop`,
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

Application calls use `*.common.svc.cluster.local`. The single chart-managed
ExternalName Service `commons-services-awe` in `far` supports rc.544's db-seed
health wait, which hardcodes that short name instead of using `aweBaseUrl`.
AWE callbacks use `http://farmer-registry-staff-portal-api.far.svc.cluster.local/
awe/webhooks/decision` (one URL, no newline) and retain HMAC authentication.
Metadata/templates and geo-widget synchronization remain enabled; geo/sample
records/images/bulk sample loaders are disabled. Novu notifications are off
because this Commons RC does not bundle Novu.

The deploy node needs `python3` with `venv` support, `pip`, `bash`, `helm`,
`kubectl` and access to PyPI/the Helm repository. Validation dependencies are
pinned in `ci/gen2/requirements.txt`. The preflight checks presence of Secret
keys without emitting their values and refuses a conflicting AWE
alias before any Helm upgrade.

## Verification

Offline checks (no credentials or cluster required):

```sh
helm repo add openg2p https://openg2p.github.io/openg2p-helm
helm dependency update helm/openg2p-farmer-registry
mkdir -p .cache/gen2-charts
helm pull openg2p/openg2p-commons-base --version 2.3.4-rc.245 --destination .cache/gen2-charts
helm pull openg2p/openg2p-commons-services --version 2.3.4-rc.245 --destination .cache/gen2-charts
python -m pip install pytest -r ci/gen2/requirements.txt
helm lint helm/openg2p-farmer-registry \
  -f helm/openg2p-farmer-registry/environments/dev-common.yaml --strict
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
