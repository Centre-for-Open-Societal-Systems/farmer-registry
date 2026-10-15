# New dev PM trust and Farmer approval

This is an operator rollout for the existing shared `commons-services` release,
not a new PM installation. Keep Base 2.3.3, Services 2.3.4-rc.245, PM 1.0.2 and
Registry 1.2.2-rc.544. No server changes have been applied by this PR.

## Verified URLs and DNS

Read-only SSH inspection on 2026-10-15 verified Kubernetes Services,
VirtualServices, running environment variables and HTTP GETs from a Farmer pod.
All listed external Commons hostnames resolve to `13.201.58.55` from that pod.

Later on 2026-10-15 the gen2-dev `*-development.oanstaging.com` names were moved
to this box and became the public names of Keycloak, IAM, PM UI and the Farmer
Registry. The old `*.commons-dev` / `*.farmer-dev` names of those services redirect
(UIs) or proxy (APIs) to the new ones; the rows below are updated.

| Purpose | URL | Evidence / use |
| --- | --- | --- |
| PM staff UI | `https://partner-management-development.oanstaging.com` | HTTP 200; use for onboarding and reviewing requests |
| Keycloak staff issuer | `https://keycloak-development.oanstaging.com/realms/staff` | Exact `issuer` returned by OIDC discovery |
| Token endpoint | `https://keycloak-development.oanstaging.com/realms/staff/protocol/openid-connect/token` | From discovery; existing secret references only |
| Internal Keycloak JWKS | `http://commons-keycloak.commons.svc.cluster.local/realms/staff/protocol/openid-connect/certs` | Same service as `http://commons-keycloak:80/...` inside Commons |
| Internal PM admin API | `http://commons-services-pm-staff-portal-api.commons.svc.cluster.local` | OpenAPI HTTP 200 identifies PM and its onboarding/approve routes |
| Internal PM key API | `http://commons-services-pm-partner-api.commons.svc.cluster.local` | `/keys/farmer-partner` currently returns 404 |
| PM key API ingress | `https://partner-management-partner-api.commons-dev.oanstaging.com` | Configured VirtualService destination is PM partner API |
| Intended PM admin ingress | `https://partner-management-staff-portal-api.commons-dev.oanstaging.com` | DNS resolves; **not currently routed to PM**; overlay adds this route |
| IAM | `https://staff-iam-development.oanstaging.com` | OpenAPI HTTP 200 identifies IAM, not PM |
| AWE | `https://awe.commons-dev.oanstaging.com` | `/v1/awe/health` returns 200; API prefix `/v1/awe/`, UI at `/` |
| Internal AWE | `http://commons-services-awe.commons.svc.cluster.local` | Shared service in Commons |
| Farmer UI | `https://farmer-registry-development.oanstaging.com` | Configured Farmer UI route |
| Registry partner API | `https://partner-farmer-development.oanstaging.com` | Configured Registry partner route |
| Registry staff API | `https://staff-farmer-development.oanstaging.com` | Configured Registry staff route |

DNS resolution alone does not establish routing. Currently PM staff API and IAM
both declare the IAM host (`staff-iam-development.oanstaging.com`) on the same gateway. The
observed response is IAM. The override gives PM its own host without changing
the shared IAM hostname global. PM UI already uses its correct internal API.
PM logout is also changed from cluster-only Keycloak DNS to the public URL.

## Prepare and validate the Helm correction

Use [the overlay](../ci/gen2/commons-pm-new-dev.values.yaml) under the owning
Commons release configuration. The two auth prefixes must agree: PM 1.0.2 gives
explicit `PARTNER_MANAGER_AUTH_*` values precedence over `COMMON_AUTH_*`.
Trust the public issuer while fetching signing keys through internal DNS.
Keep authentication and the `partner_manager` client role enforced.

The following commands run in the operator's existing trusted deployment
workspace. Saved values and rendered manifests can contain secrets: keep them
outside Git and do not attach them to a PR. Use the existing kubeconfig context.

```sh
helm history commons-services -n commons
helm get values commons-services -n commons -o yaml > commons-services.before.yaml
helm template commons-services openg2p/openg2p-commons-services \
  --version 2.3.4-rc.245 --namespace commons \
  -f commons-services.before.yaml -f ci/gen2/commons-pm-new-dev.values.yaml \
  > commons-services.candidate.yaml
python ci/gen2/check_pm_manifest.py commons-services.candidate.yaml
```

Preserve additional approved issuer/JWKS pairs if preflight finds any. Review
the rendered diff and Helm hooks through the deployment's usual release process;
only PM's auth environment, PM API host and PM logout should intentionally change.
Persist the overlay in that deployment configuration so later upgrades retain it.
Do not apply it as Farmer Helm values or use a temporary `kubectl set env` repair.

Before activation of the partner, pause pipeline
`ad8ac90635574462ac461741f336a0c7` in the connector UI and let its active run finish.
Keep it paused until the registry gates below pass. Apply the reviewed Commons
values through its owning Helm/Rancher process at the same pinned chart version.

After rollout, export live Deployments/VirtualServices to a local protected file
and run the same guard. Check PM UI login/logout, IAM login, and the new PM API
`/openapi.json` title. Verify TLS normally; do not bypass certificate validation.
Use a fresh Registry service token to call internal PM `/partners/farmer-partner`:
before onboarding, 404 is expected; 401/403 means auth is still not fixed.
Check missing/invalid tokens are rejected, and a valid token without the required
role is forbidden. Never print tokens, client secrets or private keys.

## Native PM onboarding and approval

Use the PM UI above, signed in as an authorized PM administrator, or the same
native staff API. Do not use the Registry ingestion service account to make
production onboarding decisions.

1. Inspect `/partners/farmer-partner` and
   `/partners/requests?partner_id=farmer-partner`. If active with matching keys,
   verify and reuse it. If created with one matching open onboarding request,
   review that request. Stop on disabled, conflicting, rejected-only or multiple
   pending states; do not silently re-enable, create aliases or approve unrelated
   requests.
2. Obtain the connector's actual public key from its owner/configured signing
   source. Compare its SHA-256 SPKI fingerprint and `kid`. The private key stays
   at the connector; local demo keys must not be used on dev.
3. If absent, create `POST /partners/requests/onboarding` with
   `partner_id: farmer-partner`, name `Farmer ODK Connector`, organisation
   `COSS`, description identifying this pipeline, and `keys` containing the
   verified public PEM and configured `kid`. Omit `algorithm` for PM detection;
   do not generate replacement signing keys as part of this fix.
4. Verify the created request's partner ID and proposed fingerprint. Before
   approval, the partner is `created` and key fetch must return 404.
5. The authorized reviewer uses
   `POST /partners/requests/{request_id}/approve` with review notes. Verify the
   request is `approved`, partner is `active`, and key fetch returns the matching
   key. Check `/partners/farmer-partner/audit` for submitter, reviewer and key events.

PM 1.0.2 returns HTTP 400 with application code `PM-REQ-409` for a repeated
decision; do not retry it as a transient error. Its native PM request approval
is separate from Registry AWE. No new approval engine is introduced.

## Controlled ODK to AWE verification

The schema gate still fails on 24 string coordinate columns. Complete the
backed-up [registry migration prerequisites](registry-platform-1.2.2-upgrade.md),
document-history migration and [seed repairs](gen2-db-seed-diagnosis.md), then
deploy the reviewed Farmer RC artifacts. Do not replay into an incompatible
schema. Use `ci/gen2/check_geo_schema.py` in the existing staff API pod for the
read-only gate; it invokes no application startup or migrations.

Retain `FARMER_ODK_MODEL` -> intake `a1a4d25a-1cd4-4356-abac-8782382649` ->
`registry.intake_form.farmer`. Verify AWE's active policy, configured approver
resolution, Registry callback reachability and HMAC secret binding. Preserve
existing approval stages; an absent approver is a configuration failure, not
permission to bypass approval.

With scheduling paused, inspect the source event's `farmer_profile:<instance-id>`
message correlation and replay **one** DLQ entry only if it has not been accepted.
Trace message -> ingestion -> intake -> AWE request/tasks -> signed terminal
callback -> promotion. An HTTP 200 or connector success alone is not completion.
Before approval, verify no promoted Farmer record exists. Have an assigned
approver decide through the staff UI; verify final records retain attachments,
geography and male-plus-female Family Size. Reject and duplicate-delivery cases
must be exercised on synthetic local records, not on an operator's dev record.

The existing `test/sanity/tests/test_e2e_intake.py` has the ODK/AWE acceptance
case keyed by `SANITY_ODK_INSTANCE_ID`; it remains unverified on the adopted RC
until a fresh local ODK delivery is supplied. Do not run the whole local sanity
fixture suite against dev: it creates users and modifies fixture data.

Resume this pipeline after controlled success and observe two further polling
cycles for repeated failures/duplicates. On failure keep it paused, retain
sanitized correlation/error evidence and investigate. Roll back configuration
through the owning release workflow if needed; never delete audit history or
automatically reverse data migrations. PM activation does not add signature
verification to the legacy ingestion endpoint.

## Evidence and references

- Pinned Commons chart rendered locally with the current live values plus overlay:
  manifest guard passes. The same guard rejects the unmodified live issuer setup.
- Eight guard regressions pass, covering issuer/JWKS, auth enablement, role,
  shared hostname collision, duplicate routing and browser logout.
- `uv run --no-project python local/upstream/test_pm_approval.py` passes against
  local PM 1.0.2: missing/invalid auth, onboarding, pending key suppression,
  approve/reject, repeat-decision rejection, key equality, disable/enable and
  actor-linked audit events. Synthetic records are retained; approved test
  partners are disabled at completion. This does not prove dev rollout success.
- No server mutations, partner approval, pipeline pause/replay or migrations
  have been performed. Server auth-without-role and ODK end-to-end checks remain
  rollout acceptance tasks.

Upstream: [PM deployment](https://github.com/OpenG2P/openg2p-documentation/blob/latest/platform/platform-services/partner-management/deployment.md),
[PM API](https://github.com/OpenG2P/openg2p-documentation/blob/latest/platform/platform-services/partner-management/api-reference.md),
[Registry AWE](https://github.com/OpenG2P/openg2p-documentation/blob/latest/products/registry/registry/design/awe-integration.md).
The installed versions' contracts take precedence over newer documentation.
