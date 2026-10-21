# Registry-owned dashboard delivery

The UI and API remain independent source repositories; this registry's CI builds
their Dockerfiles and owns their deployment. The API resources remain in
`helm/openg2p-farmer-registry`; the UI chart is now maintained here at
`helm/farmer-registry-dashboard`. Existing Helm release and resource names are
preserved. The UI/API repositories contain no production deployment pipeline.

All environment URLs, cookie domains, auth client/audience/roles, image refs,
ingress and Secret references are configured in these registry Helm charts and
their environment overlays. `dashboardApi.auth` owns API trust; old reserved
auth names in `dashboardApi.env` must be moved there before rendering.

The UI setup hook provisions its Keycloak client/roles and IAM tile; it grants
no staff user by default. Approved users must be assigned their dashboard client
role through IAM policy. The chart smoke hook follows setup and requires real
chart rows with the service-account credentials, plus anonymous/invalid-token
401 responses. Open `/health` checks alone are not rollout verification.

Merge the corrected API/UI source PRs before the registry integration. Pin or
override the reviewed source refs in registry CI during integration; do not use
mutable source assumptions as evidence of an image build. Existing image-only,
ownership, hook-rehearsal, backup and staging guards remain effective. Farmer's
coordinator can block deployment until hook rehearsal/environment evidence is
provided; this change does not fabricate that evidence or relax those guards.

Before deployment, verify that the selected namespace has the configured IAM,
Keycloak bootstrap Secret and pull access, and that the configured public host
is under the IAM cookie domain. Merging these PRs does not change a live cluster.
Remove the old registry paths from `oan_dashboards` during the coordinated cutover.

## Staff portal tiles

The development UI uses the shared staff IAM at
`https://staff-iam.development.oanstaging.com`, its
`.development.oanstaging.com` cookie domain and the existing
`istio-system/development` Gateway. The UI setup hook registers the tile in
that IAM after provisioning its client and `Dashboard Viewer` role. No staff
user receives the role automatically. After an approved assignment, sign in
again so the staff session contains the new client role. IAM renders a
registered tile disabled for users without that client's role.

Merging UI/API source does not register a tile. Merge this registry delivery
change and run the registry CI build/deployment with its existing guards.
Require the UI's IAM setup and authenticated chart smoke hooks to succeed;
then confirm its tile in the central staff portal and open it with an
approved viewer account. The UI's header links back to that central portal.

The dashboard UI permits its first installation explicitly. It still requires
matching hook rehearsal evidence and the API dependency to deploy successfully;
no existing release is adopted or replaced by another owner.
