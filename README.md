# OAN Farmer Registry

The OAN extension adds Farmer, household, land, crop, livestock, membership and
identity workflows to the published OpenG2P Farmer 1.2 runtime. The candidate
uses platform **1.2.2-rc.557**. Forms use section schemas, registered widgets,
themes and language metadata; behavior uses registered extension services.
OpenG2P framework and worker sources remain unchanged.

This delivery branch composes the reviewed OAN source with the existing COSS
delivery tooling. **Promotion remains blocked.** Source checks and disposable
database rehearsals do not establish live acceptance. Read the
[candidate scope and remaining checks](docs/refactor-candidate.md) before using
historical operational instructions.

| Directory | Purpose |
| --- | --- |
| `oan-extension/` | OAN models, registered services, metadata, ODK enrichment and reporting |
| `farmer-extension/` | Upstream Farmer domain reference, retained for standard extension composition |
| `ui/staff-ui/overrides/` | Registered OAN widgets and supported source overlays |
| `docker/oan/` | Images extending the published Farmer runtime |
| `ci/` | Existing Jenkins delivery plus source and native metadata checks |
| `odk/` | Source XLSForms and unpublished candidate form |
| `tests/` | Delivery, integration and regression checks |
| `docs/` | Current guides and dated historical evidence |

Helm ownership is centralized in
[COSS oan-helm](https://github.com/Centre-for-Open-Societal-Systems/oan-helm).
The [deployment profile](ci/deploy/oan-chart.json) pins an immutable chart and
SHA-256 checksum. Dashboard UI/API and connector releases have independent
owners; this candidate does not replace their running releases.

FIN is entered in the Fayda verification popup. The form displays its backing
value without a second editable FIN field. A typed value alone does not establish
verification. Existing approved identity proof survives a failed verification.
Offline ODK identity evidence remains unverified until normal approval.

For delivery tests, install `ci/validation/requirements.txt` and run
`python -m pytest tests/unit`. Native extension and repeatable metadata checks
run against the published runtime in CI; browser checks exercise the registered
widget and native data paths. See [the documentation index](docs/README.md),
[native ODK intake](docs/odk-native-intake.md) and
[New Dev delivery](docs/NEW_DEV_FARMER_FIRST.md).

Local acceptance runs serially: Commons + Farmer + Crop, then Commons + Farmer +
Livestock. Existing New Dev and staging deployments are unchanged by publication
of this candidate.
