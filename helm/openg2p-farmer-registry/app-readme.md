# OpenG2P Farmer Registry

A ready-to-install **Farmer Registry** built on the OpenG2P registry platform.

This package is a thin overlay over the shared **openg2p-registry** chart: it
adds the farmer domain (registers, schemas, seed metadata and DCI templates) via
the farmer-built images, and reuses the platform's service templates, IAM/Keycloak
wiring, db-seed machinery and sanity suite unchanged.

- **Platform chart & images:** published by
  [registry-platform](https://github.com/OpenG2P/registry-platform); this chart
  pins a specific `openg2p-registry` version as a dependency.
- **What to set:** the ingress host (`global.registryHostname`) and, for a real
  environment, the shared commons endpoints (Postgres, Keycloak, Consent/Partner
  Management, AWE, Audit) via the inherited `global.*` values.
- **Sanity suite:** set `registry.sanity.runE2e=true` to run the full end-to-end
  check (DCI search + change-request → AWE approval) after install.

COSS application repositories are declared in `values.yaml` under
`cossAddons.components`:

| Add-on | Application source | Helm owner |
| --- | --- | --- |
| Farmer dashboard | `Centre-for-Open-Societal-Systems/oan_farmerregistry_dashboard` | `farmer-registry-dashboard` |
| Farmer dashboard API | `Centre-for-Open-Societal-Systems/farmer-registry-dashboard-api` | `farmer-registry`, through `dashboardApi.image` |
| Registry connector | `OpenG2P/registry-connector` | `farmer-registry-connector` |

Jenkins reads this Helm catalogue directly. It builds the dashboard repositories'
`develop` branches for dev and `staging` branches for staging. Missing application
files preserve deployed services. The API is updated by image only, preserving
the Registry release's other resources and suppressing setup Jobs. The connector
uses a pinned upstream develop commit and separate storage; its preparation
values keep ingestion stopped. No livestock, crop or shared dashboard is owned
by this Farmer chart.

These Git repositories are application sources, rather than Helm chart indexes.
Only the pinned platform chart is a Helm dependency: making the connector a
dependency would couple Registry upgrades and removal to connector ingestion.

See the deployment docs at [docs.openg2p.org](https://docs.openg2p.org).
