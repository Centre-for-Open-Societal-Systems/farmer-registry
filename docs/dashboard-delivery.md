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
